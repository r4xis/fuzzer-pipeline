#!/usr/bin/env python3
"""
Reads CASR .casrep JSON reports and inserts crash data into PostgreSQL.
Usage: triage.py <casr_output_dir> <session_id>
"""

import json
import sys
import os
import hashlib
import shutil
from pathlib import Path

import psycopg2

DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 5432,
    "dbname": "fuzzer_db",
    "user": "fuzzer",
    "password": os.environ.get("FUZZER_DB_PASSWORD", ""),
}

POC_ARCHIVE_DIR = Path("/data/poc_archive/nsf")


def compute_input_hash(stacktrace: list) -> str:
    """Hash the top 4 stack frames to dedup crashes with the same root cause."""
    top_frames = stacktrace[:4]
    joined = "|".join(top_frames)
    return hashlib.sha256(joined.encode()).hexdigest()


def compute_file_sha256(filepath: Path) -> str:
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def archive_poc(original_crash_path: Path, crash_id: int) -> Path:
    """Copy the crashing input to the permanent POC archive."""
    POC_ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)
    dest = POC_ARCHIVE_DIR / f"crash_{crash_id:04d}.nsf"
    shutil.copy(original_crash_path, dest)
    return dest


def parse_casrep(casrep_path: Path) -> dict:
    with open(casrep_path, "r") as f:
        return json.load(f)


def find_original_crash_file(casrep_path: Path) -> Path:
    """
    The .casrep file is named '<original_crash_filename>.casrep'.
    The original crash file sits next to it, without the .casrep suffix.
    """
    original_name = casrep_path.name.removesuffix(".casrep")
    return casrep_path.parent / original_name


def insert_crash(conn, session_id: int, report: dict, poc_path: Path) -> int:
    stacktrace = report.get("Stacktrace", [])
    input_hash = compute_input_hash(stacktrace)

    severity = report.get("CrashSeverity", {})
    asan_report = report.get("AsanReport", [])
    asan_summary = next(
        (line for line in asan_report if line.startswith("SUMMARY:")), ""
    )
    source_context = report.get("Source", [])

    poc_sha256 = compute_file_sha256(poc_path)
    poc_size = poc_path.stat().st_size

    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO crashes (
                session_id, crash_line, severity_type, severity_desc,
                severity_explain, stacktrace, asan_summary, source_context,
                input_hash, poc_file_path, poc_file_size, poc_file_sha256
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (input_hash) DO NOTHING
            RETURNING id
            """,
            (
                session_id,
                report.get("CrashLine", ""),
                severity.get("Type", ""),
                severity.get("ShortDescription", ""),
                severity.get("Explanation", ""),
                stacktrace,
                asan_summary,
                source_context,
                input_hash,
                str(poc_path),
                poc_size,
                poc_sha256,
            ),
        )
        row = cur.fetchone()
        conn.commit()
        return row[0] if row else None


def main():
    if len(sys.argv) != 3:
        print("Usage: triage.py <casr_output_dir> <session_id>")
        sys.exit(1)

    casr_dir = Path(sys.argv[1])
    session_id = int(sys.argv[2])

    casrep_files = list(casr_dir.rglob("*.casrep"))
    print(f"Found {len(casrep_files)} CASR reports")

    conn = psycopg2.connect(**DB_CONFIG)

    inserted = 0
    skipped = 0

    for casrep_path in casrep_files:
        report = parse_casrep(casrep_path)
        original_crash = find_original_crash_file(casrep_path)

        if not original_crash.exists():
            print(f"  [!] Original crash file missing for {casrep_path.name}")
            continue

        crash_id = insert_crash(conn, session_id, report, original_crash)

        if crash_id:
            final_path = archive_poc(original_crash, crash_id)
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE crashes SET poc_file_path = %s WHERE id = %s",
                    (str(final_path), crash_id),
                )
                conn.commit()
            print(f"  [+] Inserted crash id={crash_id}: {report.get('CrashLine')}")
            inserted += 1
        else:
            print(f"  [=] Duplicate, skipped: {report.get('CrashLine')}")
            skipped += 1

    conn.close()
    print(f"\nDone. Inserted: {inserted}, Skipped (duplicates): {skipped}")


if __name__ == "__main__":
    main()

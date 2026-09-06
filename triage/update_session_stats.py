#!/usr/bin/env python3
"""
Runs afl-whatsup inside the fuzzing container, parses summary stats,
and updates the current session's coverage_pct and total_execs in the DB.

Usage: update_session_stats.py <target_id>
"""

import subprocess
import re
import sys
import os

import psycopg2

DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 5432,
    "dbname": "fuzzer_db",
    "user": "fuzzer",
    "password": os.environ.get("FUZZER_DB_PASSWORD", ""),
}


def get_whatsup_output() -> str:
    result = subprocess.run(
        ["docker", "exec", "fuzzer-master", "afl-whatsup", "/data/afl-output"],
        capture_output=True, text=True, timeout=30,
    )
    return result.stdout


def parse_coverage_pct(text: str) -> float | None:
    match = re.search(r"Coverage reached\s*:\s*([\d.]+)%", text)
    return float(match.group(1)) if match else None


def parse_total_execs(text: str) -> int | None:
    """
    afl-whatsup prints totals like 'Total execs : 1 millions, 708 thousands'
    or a plain number like 'Total execs : 335 thousands'. This normalizes
    that into a raw integer.
    """
    match = re.search(r"Total execs\s*:\s*(.+)", text)
    if not match:
        return None

    raw = match.group(1).strip()
    total = 0
    for value, unit in re.findall(r"([\d.]+)\s*(millions|thousands|)", raw):
        if not value:
            continue
        value = float(value)
        if unit == "millions":
            total += int(value * 1_000_000)
        elif unit == "thousands":
            total += int(value * 1_000)
        else:
            total += int(value)
    return total if total > 0 else None


def get_or_create_session(conn, target_id: int) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id FROM sessions
            WHERE target_id = %s
            ORDER BY started_at DESC
            LIMIT 1
            """,
            (target_id,),
        )
        row = cur.fetchone()
        if row:
            return row[0]

        cur.execute(
            """
            INSERT INTO sessions (target_id, started_at)
            VALUES (%s, now())
            RETURNING id
            """,
            (target_id,),
        )
        conn.commit()
        return cur.fetchone()[0]


def update_session(conn, session_id: int, coverage_pct: float, total_execs: int):
    with conn.cursor() as cur:
        cur.execute(
            """
            UPDATE sessions
            SET coverage_pct = %s,
                total_execs = %s
            WHERE id = %s
            """,
            (coverage_pct, total_execs, session_id),
        )
        conn.commit()


def main():
    if len(sys.argv) != 2:
        print("Usage: update_session_stats.py <target_id>")
        sys.exit(1)

    target_id = int(sys.argv[1])

    output = get_whatsup_output()
    coverage_pct = parse_coverage_pct(output)
    total_execs = parse_total_execs(output)

    if coverage_pct is None or total_execs is None:
        print("Could not parse afl-whatsup output, skipping update.")
        print(output)
        sys.exit(1)

    conn = psycopg2.connect(**DB_CONFIG)
    session_id = get_or_create_session(conn, target_id)
    update_session(conn, session_id, coverage_pct, total_execs)
    conn.close()

    print(f"Updated session {session_id}: coverage={coverage_pct}%, execs={total_execs}")


if __name__ == "__main__":
    main()

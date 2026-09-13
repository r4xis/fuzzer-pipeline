#!/usr/bin/env python3
# Historical record: run once on 2026-09-13 against production fuzzer_db after
# dedup switched to the crash site. Deletes every finding that repeats an
# earlier finding's crash_line (the rows the API had already stopped listing)
# and removes the PoC files that no remaining row references. Not meant to be
# re-run.
#
# Env: DB_NAME, NSF_DIR, VGM_DIR (all required), DB_HOST/DB_PORT/FUZZER_DB_PASSWORD.

import os
from pathlib import Path

import psycopg2
import psycopg2.extras

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "127.0.0.1"),
    "port": int(os.environ.get("DB_PORT", 5432)),
    "dbname": os.environ["DB_NAME"],
    "user": "fuzzer",
    "password": os.environ.get("FUZZER_DB_PASSWORD", ""),
}

ARCHIVE_DIRS = [Path(os.environ["NSF_DIR"]), Path(os.environ["VGM_DIR"])]


def delete_duplicates(conn):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT c.id, c.crash_line, c.poc_file_path
            FROM crashes c
            WHERE c.id NOT IN (
                SELECT DISTINCT ON (crash_line) id
                FROM crashes
                ORDER BY crash_line, discovered_at ASC
            )
            ORDER BY c.crash_line, c.id
            """
        )
        dupes = cur.fetchall()
        for d in dupes:
            print(f"[-] delete id={d['id']} {d['crash_line']}")
        if dupes:
            cur.execute("DELETE FROM crashes WHERE id = ANY(%s)", ([d["id"] for d in dupes],))
    conn.commit()
    return len(dupes)


def cleanup_orphaned_files(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT poc_file_path FROM crashes")
        referenced = {Path(row[0]).name for row in cur.fetchall()}

    removed = 0
    for directory in ARCHIVE_DIRS:
        if not directory.exists():
            continue
        for f in sorted(directory.iterdir()):
            if f.is_file() and f.name not in referenced:
                f.unlink()
                removed += 1
                print(f"  [-] removed orphaned file {f}")
    return removed


def main():
    conn = psycopg2.connect(**DB_CONFIG)
    deleted = delete_duplicates(conn)
    orphans = cleanup_orphaned_files(conn)
    with conn.cursor() as cur:
        cur.execute("SELECT id, crash_line FROM crashes ORDER BY id")
        remaining = cur.fetchall()
    conn.close()

    print(f"\nDone. {deleted} duplicate row(s) deleted, {orphans} orphaned file(s) removed.")
    print("Remaining findings:")
    for row in remaining:
        print(f"  id={row[0]} {row[1]}")


if __name__ == "__main__":
    main()

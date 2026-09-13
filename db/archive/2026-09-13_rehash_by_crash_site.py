#!/usr/bin/env python3
# Historical record: run once on 2026-09-13 against production fuzzer_db when
# the dedup key changed from "top 4 stack frames" to "crash site". For each
# crash_line, the earliest finding gets the new site hash so future repeats
# of that site collide on input_hash and are dropped at insert time; later
# duplicates keep their old hash and are hidden by the API. Not meant to be
# re-run.

import os
import sys

import psycopg2
import psycopg2.extras

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "triage"))
from triage import compute_input_hash  # noqa: E402

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "127.0.0.1"),
    "port": int(os.environ.get("DB_PORT", 5432)),
    "dbname": os.environ.get("DB_NAME", "fuzzer_db"),
    "user": "fuzzer",
    "password": os.environ.get("FUZZER_DB_PASSWORD", ""),
}


def main():
    conn = psycopg2.connect(**DB_CONFIG)
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT DISTINCT ON (crash_line) id, crash_line, stacktrace, input_hash
            FROM crashes
            ORDER BY crash_line, discovered_at ASC
            """
        )
        keepers = cur.fetchall()

        for row in keepers:
            new_hash = compute_input_hash(row["crash_line"], row["stacktrace"] or [])
            if new_hash == row["input_hash"]:
                print(f"[=] id={row['id']} already keyed on site {row['crash_line']}")
                continue
            cur.execute("UPDATE crashes SET input_hash = %s WHERE id = %s", (new_hash, row["id"]))
            print(f"[+] id={row['id']} {row['crash_line']} -> {new_hash}")

    conn.commit()
    conn.close()
    print(f"\nDone. {len(keepers)} crash site(s) keyed.")


if __name__ == "__main__":
    main()

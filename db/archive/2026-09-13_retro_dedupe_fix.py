#!/usr/bin/env python3
# Historical record: run once on 2026-09-13 against production fuzzer_db.
# Fixed stale poc_file_path (nsf/ -> vgm/, 8 rows) left over from the old
# hardcoded NSF archive path, and collapsed 9 duplicate crash rows that
# pre-dated the hex-address-strip fix in compute_input_hash() (17 -> 8
# rows), removing their now-orphaned PoC files. Not meant to be re-run.

import os
import shutil
import sys
from collections import defaultdict
from pathlib import Path

import psycopg2
import psycopg2.extras

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "triage"))
from triage import compute_input_hash  # noqa: E402

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "127.0.0.1"),
    "port": int(os.environ.get("DB_PORT", 5432)),
    "dbname": os.environ["DB_NAME"],
    "user": "fuzzer",
    "password": os.environ.get("FUZZER_DB_PASSWORD", ""),
}

NSF_DIR = Path(os.environ["NSF_DIR"])
VGM_DIR = Path(os.environ["VGM_DIR"])


def fix_poc_paths(conn):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT c.id, c.poc_file_path
            FROM crashes c
            LEFT JOIN sessions s ON c.session_id = s.id
            LEFT JOIN targets t ON s.target_id = t.id
            WHERE t.focus = 'VGM' AND c.poc_file_path LIKE '/data/poc_archive/nsf/%'
            ORDER BY c.id
            """
        )
        rows = cur.fetchall()

    print(f"[paths] {len(rows)} VGM crash(es) with a stale nsf/ path:")
    for row in rows:
        old_path = Path(row["poc_file_path"])
        new_path = VGM_DIR / old_path.name
        src = NSF_DIR / old_path.name
        dst = VGM_DIR / old_path.name

        if not src.exists():
            print(f"  [!] id={row['id']}: source file missing at {src}, skipping")
            continue

        shutil.move(str(src), str(dst))
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE crashes SET poc_file_path = %s WHERE id = %s",
                (str(new_path), row["id"]),
            )
        print(f"  [+] id={row['id']}: {old_path} -> {new_path}")
    conn.commit()
    return len(rows)


def fix_duplicate_hashes(conn):
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT id, stacktrace, discovered_at, input_hash FROM crashes ORDER BY id")
        rows = cur.fetchall()

    groups = defaultdict(list)
    for row in rows:
        new_hash = compute_input_hash(row["stacktrace"] or [])
        groups[new_hash].append(row)

    updated = 0
    deleted = 0
    for new_hash, group in groups.items():
        group.sort(key=lambda r: r["discovered_at"])
        keeper = group[0]
        dupes = group[1:]

        if dupes:
            dupe_ids = [d["id"] for d in dupes]
            print(
                f"[hash] group -> keep id={keeper['id']} "
                f"(discovered_at={keeper['discovered_at']}), "
                f"delete ids={dupe_ids}, new_hash={new_hash}"
            )
            # Delete duplicates first: a dupe may currently hold the exact
            # hash value we're about to assign to the keeper, and input_hash
            # is UNIQUE, so updating first would collide with it.
            with conn.cursor() as cur:
                cur.execute("DELETE FROM crashes WHERE id = ANY(%s)", (dupe_ids,))
            deleted += len(dupe_ids)

        with conn.cursor() as cur:
            cur.execute(
                "UPDATE crashes SET input_hash = %s WHERE id = %s",
                (new_hash, keeper["id"]),
            )
        updated += 1

    conn.commit()
    return updated, deleted


def cleanup_orphaned_files(conn):
    """Delete archive files no longer referenced by any crashes.poc_file_path."""
    with conn.cursor() as cur:
        cur.execute("SELECT poc_file_path FROM crashes")
        referenced = {Path(row[0]).name for row in cur.fetchall()}

    removed = []
    for directory in (NSF_DIR, VGM_DIR):
        if not directory.exists():
            continue
        for f in sorted(directory.iterdir()):
            if f.is_file() and f.name not in referenced:
                f.unlink()
                removed.append(str(f))
                print(f"  [-] removed orphaned file {f}")
    return removed


def main():
    conn = psycopg2.connect(**DB_CONFIG)

    moved = fix_poc_paths(conn)
    kept, deleted = fix_duplicate_hashes(conn)
    orphans = cleanup_orphaned_files(conn)

    conn.close()
    print(
        f"\nDone. Moved {moved} file(s). {kept} row(s) kept/rehashed, "
        f"{deleted} duplicate(s) deleted, {len(orphans)} orphaned file(s) removed."
    )


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
One-off operator script: re-resolves crash_line / stacktrace for rows
already in the database whose CrashLine never got symbolized at ingest time
(raw "<module>+0x<offset>" addresses -- see symbolize.py and README.md for
why, and triage.py for the same fix applied to new crashes going forward).

Dry-run by default: prints id, old -> new, and whether the embedded BuildId
matched the harness binary in the given image, without touching the
database. Pass --apply to actually write the resolved crash_line/stacktrace.

Note: this only updates crash_line/stacktrace, never input_hash, so it
can't violate the column's uniqueness constraint when two existing rows
turn out to resolve to the same site (that's the bug this is fixing -- the
frontend already dedups duplicate rows by crash_line for display). A new
crash at one of these now-corrected sites, ingested after this runs, will
still get its own row if it lands on a row this script updated, since that
row's input_hash was never recomputed; triage.py's own fix prevents this
going forward for sites that resolve correctly from their very first crash.

Usage:
  resymbolize_existing.py --image IMAGE [--harness PATH] [--apply]

IMAGE is required and never defaulted or looked up (e.g. via `docker
inspect`) -- pass the exact image the crashes being fixed came from
(`docker inspect <container> --format '{{.Image}}'` on the host that ran
them), since offline symbolization is only ever correct against the binary
that actually produced the crash. Test only against a disposable database
(see CLAUDE.md's "Local testing" rules) -- never run this here against
production.
"""

import argparse
import os

import psycopg2
import psycopg2.extras

from symbolize import MODULE_OFFSET_RE, harness_build_id, resolve_crash_site

FUZZER_DB_PASSWORD = os.environ.get("FUZZER_DB_PASSWORD")
if not FUZZER_DB_PASSWORD:
    raise RuntimeError("FUZZER_DB_PASSWORD environment variable is required")

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "127.0.0.1"),
    "port": int(os.environ.get("DB_PORT", 5432)),
    "dbname": "fuzzer_db",
    "user": "fuzzer",
    "password": FUZZER_DB_PASSWORD,
}

HARNESS_PATH_DEFAULT = os.environ.get("HARNESS", "/fuzzing/harness")


def candidate_rows(conn):
    """Every crash whose crash_line still looks like a raw module+offset
    address. The SQL side is just a cheap prefilter (LIKE); the exact shape
    is confirmed in Python so this doesn't depend on a SQL regex dialect."""
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT id, crash_line, stacktrace FROM crashes WHERE crash_line LIKE '%+0x%'")
        rows = cur.fetchall()
    return [row for row in rows if MODULE_OFFSET_RE.match((row["crash_line"] or "").strip())]


def apply_update(conn, crash_id: int, new_crash_line: str, new_stacktrace: list):
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE crashes SET crash_line = %s, stacktrace = %s WHERE id = %s",
            (new_crash_line, new_stacktrace, crash_id),
        )
        conn.commit()


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--image", required=True,
        help="image to run llvm-readelf/llvm-symbolizer in -- the exact image the crashes being "
             "fixed came from, e.g. from `docker inspect <container> --format '{{.Image}}'`",
    )
    parser.add_argument(
        "--harness", default=HARNESS_PATH_DEFAULT,
        help=f"harness path inside the image (default: {HARNESS_PATH_DEFAULT})",
    )
    parser.add_argument(
        "--apply", action="store_true",
        help="write resolved crash_line/stacktrace to the database (default: dry run, prints only)",
    )
    args = parser.parse_args()

    print(f"Using image: {args.image}")
    print(f"Harness path: {args.harness}")

    build_id = harness_build_id(args.image, args.harness)
    print(f"Harness Build ID in that image: {build_id or '(could not read it -- nothing will resolve)'}\n")

    conn = psycopg2.connect(**DB_CONFIG)
    rows = candidate_rows(conn)
    print(f"Found {len(rows)} row(s) with an unresolved crash_line\n")

    resolved_count = 0
    for row in rows:
        result = resolve_crash_site(row["crash_line"], row["stacktrace"] or [], args.image, args.harness)
        match_label = {True: "yes", False: "no", None: "n/a"}[result.build_id_match]
        if result.resolved:
            print(f"id={row['id']}: {row['crash_line']!r} -> {result.crash_line!r}  [BuildId match: {match_label}]")
            resolved_count += 1
            if args.apply:
                apply_update(conn, row["id"], result.crash_line, result.stacktrace)
        else:
            print(f"id={row['id']}: unchanged  [BuildId match: {match_label}] -- {result.reason}")

    conn.close()

    mode = "Applied" if args.apply else "Would resolve"
    print(f"\n{mode} {resolved_count} of {len(rows)} row(s).")
    if not args.apply and resolved_count:
        print("Dry run only -- pass --apply to write these changes.")


if __name__ == "__main__":
    main()

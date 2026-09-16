#!/usr/bin/env python3
"""
Runs afl-whatsup inside the fuzzing container, parses summary stats,
and updates the current session's coverage_pct and total_execs in the DB.

The session also tracks the run it describes: the master's start_time from
fuzzer_stats is stored as sessions.fuzzer_started_at. When the master is
found running with a different start_time (the fuzzers were restarted for
the same target) the session's readings are wiped and recorded afresh while
its findings are kept. When the master container is not running the session
is marked ended and nothing is recorded.

Usage: update_session_stats.py <target_id>
"""

import subprocess
import re
import sys
import os
from datetime import datetime, timezone
from typing import List, Optional, TypedDict

import psycopg2


class InstanceStats(TypedDict):
    instance_name: str
    coverage_pct: Optional[float]
    execs_per_sec: Optional[float]
    crashes_saved: Optional[int]

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "127.0.0.1"),
    "port": int(os.environ.get("DB_PORT", 5432)),
    "dbname": "fuzzer_db",
    "user": "fuzzer",
    "password": os.environ.get("FUZZER_DB_PASSWORD", ""),
}

AFL_MASTER_CONTAINER = os.environ.get("AFL_MASTER_CONTAINER", "fuzzer-master")
AFL_OUTPUT = os.environ.get("AFL_OUTPUT", "/data/afl-output")


def master_running() -> bool:
    result = subprocess.run(
        ["docker", "inspect", "-f", "{{.State.Running}}", AFL_MASTER_CONTAINER],
        capture_output=True, text=True, timeout=30,
    )
    return result.returncode == 0 and result.stdout.strip() == "true"


def get_whatsup_output() -> str:
    result = subprocess.run(
        ["docker", "exec", AFL_MASTER_CONTAINER, "afl-whatsup", AFL_OUTPUT],
        capture_output=True, text=True, timeout=30,
    )
    return result.stdout


def get_fuzzer_start_time() -> Optional[datetime]:
    """
    start_time from the master's fuzzer_stats: the moment this afl-fuzz
    process began, which changes on every restart (a resume included).
    Read through the container because the output directory is root-owned.
    """
    result = subprocess.run(
        ["docker", "exec", AFL_MASTER_CONTAINER, "cat", f"{AFL_OUTPUT}/fuzzer0/fuzzer_stats"],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        return None
    match = re.search(r"^start_time\s*:\s*(\d+)", result.stdout, re.MULTILINE)
    if not match:
        return None
    return datetime.fromtimestamp(int(match.group(1)), tz=timezone.utc)


def parse_coverage_pct(text: str) -> Optional[float]:
    match = re.search(r"Coverage reached\s*:\s*([\d.]+)%", text)
    return float(match.group(1)) if match else None


def parse_total_execs(text: str) -> Optional[int]:
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


INSTANCE_HEADER_RE = re.compile(r">>>.*?instance:\s*(\S+).*?<<<")
INSTANCE_COVERAGE_RE = re.compile(r"coverage\s*:?\s*([\d.]+)%")
INSTANCE_SPEED_RE = re.compile(r"lifetime speed\s+([\d.]+)\s*execs/sec")
INSTANCE_CRASHES_RE = re.compile(r"crashes saved\s+(\d+)")
INSTANCE_NO_CRASHES_RE = re.compile(r"no crashes yet")


def parse_instances(text: str) -> List[InstanceStats]:
    """
    afl-whatsup prints one '>>> ... instance: fuzzer0 ... <<<' block per
    fuzzer, followed by its stats (or a "dead or running remotely" notice),
    before the aggregate "Summary stats" section. This pulls per-instance
    coverage/speed/crash counts out of each block.
    """
    summary_idx = text.find("Summary stats")
    body = text[:summary_idx] if summary_idx != -1 else text

    headers = list(INSTANCE_HEADER_RE.finditer(body))
    instances = []
    for i, header in enumerate(headers):
        name = header.group(1)
        start = header.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(body)
        block = body[start:end]

        coverage_match = INSTANCE_COVERAGE_RE.search(block)
        speed_match = INSTANCE_SPEED_RE.search(block)
        crashes_match = INSTANCE_CRASHES_RE.search(block)

        if crashes_match:
            crashes_saved = int(crashes_match.group(1))
        elif INSTANCE_NO_CRASHES_RE.search(block):
            # afl-whatsup drops "crashes saved N" entirely and prints "no
            # crashes yet" once the instance's count is zero.
            crashes_saved = 0
        else:
            # e.g. "Instance is dead or running remotely, skipping."
            crashes_saved = None

        if not (coverage_match and speed_match and crashes_saved is not None):
            continue

        instances.append(
            InstanceStats(
                instance_name=name,
                coverage_pct=float(coverage_match.group(1)),
                execs_per_sec=float(speed_match.group(1)),
                crashes_saved=crashes_saved,
            )
        )
    return instances


def latest_session(conn, target_id: int):
    """(id, fuzzer_started_at) of the target's most recent session, or None."""
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, fuzzer_started_at FROM sessions
            WHERE target_id = %s
            ORDER BY started_at DESC NULLS LAST, id DESC
            LIMIT 1
            """,
            (target_id,),
        )
        return cur.fetchone()


def mark_session_ended(conn, target_id: int) -> Optional[int]:
    """Sets ended_at on the target's latest session if it is still open."""
    session = latest_session(conn, target_id)
    if not session:
        return None
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE sessions SET ended_at = now() WHERE id = %s AND ended_at IS NULL",
            (session[0],),
        )
        conn.commit()
    return session[0]


def get_or_create_session(conn, target_id: int, fuzzer_started_at: Optional[datetime]) -> int:
    """
    Returns the session for the run currently in progress.

    - no session yet: create one for this run;
    - session without a recorded run start (rows from before this column
      existed): adopt the running master as its run, keeping the readings;
    - same run start: continue it;
    - different run start: the fuzzers were restarted for the same target.
      The session's coverage/instance readings are deleted and its clock
      reset; its findings stay attached (a repeat is not a new finding).
    """
    session = latest_session(conn, target_id)
    with conn.cursor() as cur:
        if not session:
            cur.execute(
                """
                INSERT INTO sessions (target_id, started_at, fuzzer_started_at)
                VALUES (%s, COALESCE(%s, now()), %s)
                RETURNING id
                """,
                (target_id, fuzzer_started_at, fuzzer_started_at),
            )
            session_id = cur.fetchone()[0]
            conn.commit()
            print(f"Created session {session_id} for target {target_id}")
            return session_id

        session_id, recorded_start = session
        if fuzzer_started_at is None or recorded_start is None:
            cur.execute(
                """
                UPDATE sessions
                SET fuzzer_started_at = COALESCE(fuzzer_started_at, %s), ended_at = NULL
                WHERE id = %s
                """,
                (fuzzer_started_at, session_id),
            )
            conn.commit()
            return session_id

        if abs((fuzzer_started_at - recorded_start).total_seconds()) < 1:
            cur.execute("UPDATE sessions SET ended_at = NULL WHERE id = %s", (session_id,))
            conn.commit()
            return session_id

        cur.execute("DELETE FROM coverage_history WHERE session_id = %s", (session_id,))
        history_deleted = cur.rowcount
        cur.execute("DELETE FROM fuzzer_instances WHERE session_id = %s", (session_id,))
        instances_deleted = cur.rowcount
        cur.execute(
            """
            UPDATE sessions
            SET started_at = %s, fuzzer_started_at = %s, ended_at = NULL,
                coverage_pct = NULL, total_execs = NULL
            WHERE id = %s
            """,
            (fuzzer_started_at, fuzzer_started_at, session_id),
        )
        conn.commit()
        print(
            f"Fuzzers restarted for target {target_id} (run started {fuzzer_started_at:%Y-%m-%d %H:%M:%S} UTC, "
            f"previous {recorded_start:%Y-%m-%d %H:%M:%S} UTC): reset session {session_id}, "
            f"dropped {history_deleted} history and {instances_deleted} instance readings"
        )
        return session_id


def record_session_stats(conn, session_id: int, coverage_pct: float, total_execs: int):
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
        cur.execute(
            """
            INSERT INTO coverage_history (session_id, recorded_at, coverage_pct, total_execs)
            VALUES (%s, now(), %s, %s)
            """,
            (session_id, coverage_pct, total_execs),
        )
        conn.commit()


def record_instance_stats(conn, session_id: int, instances: List[InstanceStats]):
    with conn.cursor() as cur:
        for instance in instances:
            cur.execute(
                """
                INSERT INTO fuzzer_instances
                    (session_id, instance_name, coverage_pct, execs_per_sec, crashes_saved, recorded_at)
                VALUES (%s, %s, %s, %s, %s, now())
                """,
                (
                    session_id,
                    instance["instance_name"],
                    instance["coverage_pct"],
                    instance["execs_per_sec"],
                    instance["crashes_saved"],
                ),
            )
        conn.commit()


def main():
    if len(sys.argv) != 2:
        print("Usage: update_session_stats.py <target_id>")
        sys.exit(1)

    target_id = int(sys.argv[1])

    if not master_running():
        conn = psycopg2.connect(**DB_CONFIG)
        session_id = mark_session_ended(conn, target_id)
        conn.close()
        if session_id is None:
            print(f"Master container {AFL_MASTER_CONTAINER} is not running and target {target_id} has no session.")
        else:
            print(f"Master container {AFL_MASTER_CONTAINER} is not running; session {session_id} marked ended.")
        sys.exit(0)

    output = get_whatsup_output()
    coverage_pct = parse_coverage_pct(output)
    total_execs = parse_total_execs(output)

    if coverage_pct is None or total_execs is None:
        print("Could not parse afl-whatsup output, skipping update.")
        print(output)
        sys.exit(1)

    instances = parse_instances(output)
    fuzzer_started_at = get_fuzzer_start_time()
    if fuzzer_started_at is None:
        print("Could not read start_time from fuzzer_stats; continuing without run tracking.")

    conn = psycopg2.connect(**DB_CONFIG)
    session_id = get_or_create_session(conn, target_id, fuzzer_started_at)
    record_session_stats(conn, session_id, coverage_pct, total_execs)
    record_instance_stats(conn, session_id, instances)
    conn.close()

    print(f"Updated session {session_id}: coverage={coverage_pct}%, execs={total_execs}")
    for instance in instances:
        print(
            f"  {instance['instance_name']}: coverage={instance['coverage_pct']}%, "
            f"speed={instance['execs_per_sec']}/sec, crashes={instance['crashes_saved']}"
        )
    skipped = len(INSTANCE_HEADER_RE.findall(output)) - len(instances)
    if skipped > 0:
        print(f"  ({skipped} instance(s) dead/unparseable, skipped)")


if __name__ == "__main__":
    main()

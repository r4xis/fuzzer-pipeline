import os
from typing import Literal, Optional

import psycopg2
import psycopg2.extras
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

# Docs expose the full schema (including the operator-only /crashes shape);
# keep them off in production unless explicitly opted into.
_docs_enabled = os.environ.get("ENABLE_API_DOCS") == "1"

# Set on the instance Caddy proxies to the public site: every crash-related
# response is forced to public-only, ignoring whatever the client asks for,
# and the status-update endpoint is hidden. Unset for the admin/local-dev
# instance (run bare, against the DB over an SSH tunnel), which keeps today's
# full behaviour.
PUBLIC_MODE = os.environ.get("PUBLIC_MODE") == "1"

# Redaction for PUBLIC_MODE: every finding is listed (existence is public
# either way), but a non-public row is cut down to this allowlist (plus the
# derived crash_file computed below -- never the real crash_line). Built by
# picking allowed keys *in*, never by deleting sensitive ones out, so a
# column added to a query later can't leak by default.
WITHHELD_FIELDS = ["id", "status", "discovered_at", "target_id", "session_id"]

# Extra fields a disclosed (visibility='public') row adds on top of
# WITHHELD_FIELDS. The list view never carried stack trace / source / PoC
# fields even pre-redaction, so its extra set is smaller than detail's.
PUBLIC_LIST_EXTRA_FIELDS = [
    "crash_line", "severity_type", "severity_desc", "visibility",
    "report_url", "target_focus", "program_name",
]
PUBLIC_DETAIL_EXTRA_FIELDS = PUBLIC_LIST_EXTRA_FIELDS + [
    "severity_explain", "stacktrace", "asan_summary", "source_context",
    "poc_file_size", "poc_file_sha256",
]


# Basename of the path in a "path:line[:col]" crash_line, or None if it's
# missing or doesn't parse as that shape. Never exposes the line/col or any
# directory component.
def crash_file_from_line(crash_line):
    if not crash_line:
        return None
    parts = crash_line.rsplit(":", 2)
    if len(parts) == 3 and parts[1].isdigit() and parts[2].isdigit() and parts[0]:
        path = parts[0]
    else:
        parts = crash_line.rsplit(":", 1)
        if len(parts) == 2 and parts[1].isdigit() and parts[0]:
            path = parts[0]
        else:
            return None
    return os.path.basename(path)


def redact_crash(row, public_extra_fields):
    if row["visibility"] == "public":
        out = {k: row[k] for k in WITHHELD_FIELDS + public_extra_fields}
        out["withheld"] = False
        return out
    out = {k: row[k] for k in WITHHELD_FIELDS}
    out["withheld"] = True
    out["crash_file"] = crash_file_from_line(row["crash_line"])
    return out


app = FastAPI(
    title="Fuzzer Crash Triage API",
    docs_url="/docs" if _docs_enabled else None,
    redoc_url="/redoc" if _docs_enabled else None,
    openapi_url="/openapi.json" if _docs_enabled else None,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


class CrashStatusUpdate(BaseModel):
    status: Literal["new", "triaged", "reported", "duplicate"]

# A session counts as running while it has not been marked ended by the
# collector and its newest reading is younger than this. The collector runs
# every 15 minutes, so one missed pass still reads as running.
RUNNING_WINDOW = "20 minutes"

# Per-session run state, joined by the callers below: the newest reading time
# and whether the run is still going.
SESSION_STATE_SQL = f"""
    SELECT s.id, s.target_id, s.started_at, s.ended_at, s.fuzzer_started_at,
           s.coverage_pct, s.total_execs,
           r.latest_reading_at,
           (s.ended_at IS NULL
            AND r.latest_reading_at IS NOT NULL
            AND r.latest_reading_at > now() - interval '{RUNNING_WINDOW}') AS running
    FROM sessions s
    LEFT JOIN LATERAL (
        SELECT max(recorded_at) AS latest_reading_at
        FROM coverage_history h WHERE h.session_id = s.id
    ) r ON true
"""

FUZZER_DB_PASSWORD = os.environ.get("FUZZER_DB_PASSWORD")
if not FUZZER_DB_PASSWORD:
    raise RuntimeError("FUZZER_DB_PASSWORD environment variable is required")

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "postgres"),
    "port": int(os.environ.get("DB_PORT", 5432)),
    "dbname": "fuzzer_db",
    "user": "fuzzer",
    "password": FUZZER_DB_PASSWORD,
}


def get_connection():
    return psycopg2.connect(**DB_CONFIG)


@app.get("/")
def root():
    return {"status": "ok", "service": "fuzzer-crash-triage-api"}


@app.get("/programs")
def list_programs():
    conn = get_connection()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT id, name, repo_url FROM programs ORDER BY name")
        rows = cur.fetchall()
    conn.close()
    return {"programs": rows}


@app.get("/targets")
def list_targets(program_id: Optional[int] = None):
    # Each target carries the state of its most recent session, so the
    # frontend can tell which targets are being fuzzed right now without
    # loading every session's readings.
    #
    # It also carries aggregate, detail-free crash counts (one unique site
    # per crash_line, same dedup as GET /crashes) so the frontend never needs
    # to call /crashes just to show a number.
    query = f"""
        SELECT t.id, t.program_id, t.focus, t.harness_version, t.created_at,
               ls.id AS latest_session_id,
               ls.started_at AS latest_session_started_at,
               ls.ended_at AS latest_session_ended_at,
               ls.latest_reading_at,
               COALESCE(ls.running, false) AS running,
               COALESCE(cc.total_crashes, 0) AS total_crashes,
               COALESCE(cc.public_crashes, 0) AS public_crashes
        FROM targets t
        LEFT JOIN LATERAL (
            SELECT * FROM ({SESSION_STATE_SQL}) st
            WHERE st.target_id = t.id
            ORDER BY st.started_at DESC NULLS LAST, st.id DESC
            LIMIT 1
        ) ls ON true
        LEFT JOIN LATERAL (
            -- Deduped independently per visibility, matching how GET /crashes
            -- dedups: it filters to visibility = 'public' *before* collapsing
            -- to one row per crash_line, not after. Deduping once across all
            -- rows and then checking the winner's visibility would disagree
            -- with /crashes whenever a site's earliest row is private but a
            -- later one at the same site is public (e.g. a duplicate marked
            -- public after an earlier private report).
            SELECT
                (SELECT count(*) FROM (
                    SELECT DISTINCT ON (c.crash_line) c.id
                    FROM crashes c
                    JOIN sessions cs ON c.session_id = cs.id
                    WHERE cs.target_id = t.id
                    ORDER BY c.crash_line, c.discovered_at ASC
                ) all_sites) AS total_crashes,
                (SELECT count(*) FROM (
                    SELECT DISTINCT ON (c.crash_line) c.id
                    FROM crashes c
                    JOIN sessions cs ON c.session_id = cs.id
                    WHERE cs.target_id = t.id AND c.visibility = 'public'
                    ORDER BY c.crash_line, c.discovered_at ASC
                ) public_sites) AS public_crashes
        ) cc ON true
        WHERE 1=1
    """
    params = []
    if program_id:
        query += " AND t.program_id = %s"
        params.append(program_id)
    query += " ORDER BY t.focus"

    conn = get_connection()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(query, params)
        rows = cur.fetchall()
    conn.close()
    return {"targets": rows}


@app.get("/sessions/{session_id}")
def get_session(session_id: int):
    conn = get_connection()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(f"SELECT * FROM ({SESSION_STATE_SQL}) st WHERE st.id = %s", (session_id,))
        row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Session not found")
    return row


@app.get("/sessions/{session_id}/history")
def get_session_history(session_id: int):
    conn = get_connection()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT id FROM sessions WHERE id = %s", (session_id,))
        session = cur.fetchone()
        if not session:
            conn.close()
            raise HTTPException(status_code=404, detail="Session not found")

        cur.execute(
            """
            SELECT recorded_at, coverage_pct, total_execs
            FROM coverage_history
            WHERE session_id = %s
            ORDER BY recorded_at ASC
            """,
            (session_id,),
        )
        rows = cur.fetchall()
    conn.close()
    return {"session_id": session_id, "history": rows}


@app.get("/sessions/{session_id}/instances")
def get_session_instances(session_id: int):
    conn = get_connection()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute("SELECT id FROM sessions WHERE id = %s", (session_id,))
        session = cur.fetchone()
        if not session:
            conn.close()
            raise HTTPException(status_code=404, detail="Session not found")

        cur.execute(
            """
            SELECT instance_name, coverage_pct, execs_per_sec, crashes_saved, recorded_at
            FROM fuzzer_instances
            WHERE session_id = %s
            ORDER BY recorded_at ASC
            """,
            (session_id,),
        )
        rows = cur.fetchall()
    conn.close()
    return {"session_id": session_id, "instances": rows}


@app.get("/crashes")
def list_crashes(
    visibility: Optional[str] = None,
    status: Optional[str] = None,
    target_id: Optional[int] = None,
):
    # One row per crash site: the earliest finding at each crash_line. Older
    # rows that repeat a site (ingested before dedup keyed on the site) stay
    # in the table but are never listed.
    query = """
        SELECT DISTINCT ON (c.crash_line)
               c.id, c.crash_line, c.severity_type, c.severity_desc,
               c.visibility, c.status, c.discovered_at, c.report_url,
               c.session_id, t.id AS target_id,
               t.focus AS target_focus, p.name AS program_name
        FROM crashes c
        LEFT JOIN sessions s ON c.session_id = s.id
        LEFT JOIN targets t ON s.target_id = t.id
        LEFT JOIN programs p ON t.program_id = p.id
        WHERE 1=1
    """
    params = []

    # visibility=private is the admin view and returns every row, mirroring
    # how /crashes/{id} treats it; anything else is limited to public rows.
    # In public mode every finding is listed regardless (redacted below),
    # so that admin override does not apply and is simply ignored.
    if not PUBLIC_MODE and visibility != "private":
        query += " AND c.visibility = 'public'"

    if status:
        query += " AND c.status = %s"
        params.append(status)

    if target_id:
        query += " AND t.id = %s"
        params.append(target_id)

    query += " ORDER BY c.crash_line, c.discovered_at ASC"
    query = f"SELECT * FROM ({query}) AS unique_sites ORDER BY discovered_at DESC"

    conn = get_connection()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(query, params)
        rows = cur.fetchall()
    conn.close()

    if PUBLIC_MODE:
        rows = [redact_crash(row, PUBLIC_LIST_EXTRA_FIELDS) for row in rows]

    return {"count": len(rows), "crashes": rows}


@app.get("/crashes/{crash_id}")
def get_crash(crash_id: int, visibility: Optional[str] = None):
    conn = get_connection()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT c.id, c.crash_line, c.severity_type, c.severity_desc, c.severity_explain,
                   c.stacktrace, c.asan_summary, c.source_context, c.poc_file_size,
                   c.poc_file_sha256, c.visibility, c.status, c.discovered_at, c.report_url,
                   c.session_id, t.id AS target_id,
                   t.focus AS target_focus, p.name AS program_name
            FROM crashes c
            LEFT JOIN sessions s ON c.session_id = s.id
            LEFT JOIN targets t ON s.target_id = t.id
            LEFT JOIN programs p ON t.program_id = p.id
            WHERE c.id = %s
            """,
            (crash_id,),
        )
        row = cur.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Crash not found")

    if PUBLIC_MODE:
        # 200 either way: existence is already visible via the (now
        # redacted-but-complete) /crashes list, so there is nothing a 404
        # would hide that a 200 with a withheld body doesn't already show.
        return redact_crash(row, PUBLIC_DETAIL_EXTRA_FIELDS)

    if visibility != "private" and row["visibility"] != "public":
        raise HTTPException(status_code=403, detail="This crash has not been disclosed yet")

    return row


@app.patch("/crashes/{crash_id}/status")
def update_crash_status(crash_id: int, body: CrashStatusUpdate):
    if PUBLIC_MODE:
        raise HTTPException(status_code=404, detail="Not found")

    conn = get_connection()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "UPDATE crashes SET status = %s WHERE id = %s RETURNING id, status",
            (body.status, crash_id),
        )
        row = cur.fetchone()
    conn.commit()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Crash not found")

    return row


@app.get("/crashes/{crash_id}/download")
def download_poc(crash_id: int):
    conn = get_connection()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            "SELECT poc_file_path, visibility FROM crashes WHERE id = %s",
            (crash_id,),
        )
        row = cur.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Crash not found")

    if row["visibility"] != "public":
        if PUBLIC_MODE:
            raise HTTPException(status_code=404, detail="Crash not found")
        raise HTTPException(status_code=403, detail="This crash has not been disclosed yet")

    file_path = row["poc_file_path"]
    if not os.path.exists(file_path):
        raise HTTPException(status_code=410, detail="PoC file is missing on disk")

    return FileResponse(
        file_path,
        filename=f"crash_{crash_id}{os.path.splitext(file_path)[1]}",
        media_type="application/octet-stream",
    )

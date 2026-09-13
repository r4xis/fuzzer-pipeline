import os
from typing import Literal, Optional

import psycopg2
import psycopg2.extras
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

app = FastAPI(title="Fuzzer Crash Triage API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


class CrashStatusUpdate(BaseModel):
    status: Literal["new", "triaged", "reported", "duplicate"]

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "postgres"),
    "port": int(os.environ.get("DB_PORT", 5432)),
    "dbname": "fuzzer_db",
    "user": "fuzzer",
    "password": os.environ.get("FUZZER_DB_PASSWORD", ""),
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
    query = """
        SELECT t.id, t.program_id, t.focus, t.harness_version, t.created_at,
               (SELECT s.id FROM sessions s
                WHERE s.target_id = t.id
                ORDER BY s.started_at DESC NULLS LAST
                LIMIT 1) AS latest_session_id
        FROM targets t
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
    if visibility != "private":
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

    if visibility != "private" and row["visibility"] != "public":
        raise HTTPException(status_code=403, detail="This crash has not been disclosed yet")

    return row


@app.patch("/crashes/{crash_id}/status")
def update_crash_status(crash_id: int, body: CrashStatusUpdate):
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
        raise HTTPException(status_code=403, detail="This crash has not been disclosed yet")

    file_path = row["poc_file_path"]
    if not os.path.exists(file_path):
        raise HTTPException(status_code=410, detail="PoC file is missing on disk")

    return FileResponse(
        file_path,
        filename=f"crash_{crash_id}{os.path.splitext(file_path)[1]}",
        media_type="application/octet-stream",
    )

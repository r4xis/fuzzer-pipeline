import os
from typing import Optional

import psycopg2
import psycopg2.extras
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse

app = FastAPI(title="Fuzzer Crash Triage API")

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "postgres"),
    "port": 5432,
    "dbname": "fuzzer_db",
    "user": "fuzzer",
    "password": os.environ.get("FUZZER_DB_PASSWORD", ""),
}


def get_connection():
    return psycopg2.connect(**DB_CONFIG)


@app.get("/")
def root():
    return {"status": "ok", "service": "fuzzer-crash-triage-api"}


@app.get("/crashes")
def list_crashes(visibility: Optional[str] = None, status: Optional[str] = None):
    """
    List crashes. Defaults to only public crashes for safety.
    Pass visibility=private explicitly (admin use) to see everything.
    """
    query = """
        SELECT id, crash_line, severity_type, severity_desc,
               visibility, status, discovered_at
        FROM crashes
        WHERE 1=1
    """
    params = []

    if visibility:
        query += " AND visibility = %s"
        params.append(visibility)
    else:
        query += " AND visibility = 'public'"

    if status:
        query += " AND status = %s"
        params.append(status)

    query += " ORDER BY discovered_at DESC"

    conn = get_connection()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(query, params)
        rows = cur.fetchall()
    conn.close()

    return {"count": len(rows), "crashes": rows}


@app.get("/crashes/{crash_id}")
def get_crash(crash_id: int):
    conn = get_connection()
    with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
        cur.execute(
            """
            SELECT id, crash_line, severity_type, severity_desc, severity_explain,
                   stacktrace, asan_summary, source_context, poc_file_size,
                   poc_file_sha256, visibility, status, discovered_at
            FROM crashes
            WHERE id = %s
            """,
            (crash_id,),
        )
        row = cur.fetchone()
    conn.close()

    if not row:
        raise HTTPException(status_code=404, detail="Crash not found")

    # Never leak the private disk path to API consumers
    if row["visibility"] != "public":
        raise HTTPException(status_code=403, detail="This crash has not been disclosed yet")

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
        filename=f"crash_{crash_id}.nsf",
        media_type="application/octet-stream",
    )

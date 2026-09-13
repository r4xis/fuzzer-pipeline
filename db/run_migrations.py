#!/usr/bin/env python3
"""
Applies pending SQL files from db/migrations/ in numeric order, tracking
applied versions in the schema_migrations table so each file runs once.

Usage: run_migrations.py
"""

import os
import re
import sys

import psycopg2

MIGRATIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "migrations")

DB_CONFIG = {
    "host": os.environ.get("DB_HOST", "127.0.0.1"),
    "port": int(os.environ.get("DB_PORT", 5432)),
    "dbname": "fuzzer_db",
    "user": "fuzzer",
    "password": os.environ.get("FUZZER_DB_PASSWORD", ""),
}

MIGRATION_RE = re.compile(r"^(\d+)_.+\.sql$")


def discover_migrations():
    files = []
    for name in os.listdir(MIGRATIONS_DIR):
        match = MIGRATION_RE.match(name)
        if match:
            files.append((match.group(1), name))
    files.sort(key=lambda item: int(item[0]))
    return files


def ensure_migrations_table(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version     TEXT PRIMARY KEY,
                applied_at  TIMESTAMPTZ DEFAULT now()
            )
            """
        )
    conn.commit()


def applied_versions(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT version FROM schema_migrations")
        return {row[0] for row in cur.fetchall()}


def apply_migration(conn, version, filename):
    path = os.path.join(MIGRATIONS_DIR, filename)
    with open(path) as f:
        sql = f.read()

    with conn.cursor() as cur:
        cur.execute(sql)
        cur.execute(
            "INSERT INTO schema_migrations (version, applied_at) VALUES (%s, now())",
            (version,),
        )
    conn.commit()


def main():
    conn = psycopg2.connect(**DB_CONFIG)
    ensure_migrations_table(conn)
    done = applied_versions(conn)

    for version, filename in discover_migrations():
        if version in done:
            print(f"skip  {filename} (already applied)")
            continue

        print(f"apply {filename}")
        try:
            apply_migration(conn, version, filename)
        except Exception:
            conn.rollback()
            conn.close()
            raise

    conn.close()
    print("Migrations up to date.")


if __name__ == "__main__":
    main()

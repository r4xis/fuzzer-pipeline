# api

FastAPI service over the pipeline database. Read-only for visitors: the only
mutating endpoint (`PATCH /crashes/{id}/status`) is not reachable from the
frontend (CORS allows `GET` only) and exists for operator tooling.

## Endpoints

| Method | Path | Notes |
| --- | --- | --- |
| GET | `/` | health |
| GET | `/programs` | `{programs: [{id, name, repo_url}]}` |
| GET | `/targets?program_id=` | adds `created_at` and the target's most recent session: `latest_session_id`, `latest_session_started_at`, `latest_session_ended_at`, `latest_reading_at`, `running` (no `ended_at` and a reading younger than 20 minutes) |
| GET | `/sessions/{id}` | the session row with `latest_reading_at` and `running` |
| GET | `/crashes?visibility=&status=&target_id=` | one row per crash site (the earliest finding at each `crash_line`); default: public rows only; `visibility=private` is the admin view and returns every site |
| GET | `/crashes/{id}?visibility=` | full detail; unreported/private rows need `visibility=private` |
| GET | `/crashes/{id}/download` | PoC input, `public` rows only (403 otherwise, 410 if the file is missing) |
| GET | `/sessions/{id}/history` | session coverage / exec readings, oldest first |
| GET | `/sessions/{id}/instances` | per-instance readings (`fuzzer0` master, `fuzzerN` secondaries), oldest first |
| PATCH | `/crashes/{id}/status` | body `{"status": "new" \| "triaged" \| "reported" \| "duplicate"}` |

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `DB_HOST` | `postgres` | database host (the compose service name) |
| `DB_PORT` | `5432` | |
| `FUZZER_DB_PASSWORD` | — | password for the `fuzzer` role |

Database name and user are fixed to `fuzzer_db` / `fuzzer`.

## Running

In production it runs as the `api` compose service (built from this
directory, `/data` mounted so PoC downloads can read the archive).

Locally, against a tunnelled database:

```
pip install -r requirements.txt
DB_HOST=localhost DB_PORT=5433 FUZZER_DB_PASSWORD=... uvicorn main:app --reload --port 8000
```

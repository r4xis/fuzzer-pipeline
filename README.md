# fuzzer-pipeline

A continuous, coverage-guided fuzzing pipeline with automated crash triage and
a public disclosure site. An AFL++ cluster fuzzes a target library around the
clock; every crash it finds is triaged, deduplicated and stored with its
proof-of-concept input; coverage and per-instance statistics are recorded over
time; and a read-only web frontend publishes the findings once they have been
reported to the maintainers.

The target is deliberately not part of this repository's identity: a *program*
(the library under test) and its *targets* (one per input format / harness)
are rows in the database, so the same pipeline can be pointed at a new target
without changing the code.

## How it works

```
 ┌───────────────────────────── Docker host ─────────────────────────────┐
 │                                                                       │
 │  fuzzer0 (AFL++ -M)  fuzzer1 (-S)  fuzzer2 (-S)  fuzzer3 (-S)         │
 │        └───────────────┴───────────────┴───────────────┘              │
 │                          /data (shared volume)                        │
 │             afl-output/ · seeds/ · poc_archive/ · backups/            │
 │                                │                                      │
 │        cron, every 15 min ─────┤                                      │
 │        ├─ triage/update_session_stats.py   afl-whatsup → coverage,    │
 │        │                                   per-instance readings      │
 │        └─ triage/triage.py                 CASR reports → crashes,    │
 │                                            dedupe, PoC archive        │
 │                                │                                      │
 │                           PostgreSQL                                  │
 │                                │                                      │
 │                        api/ (FastAPI, :8000)                          │
 └────────────────────────────────┼──────────────────────────────────────┘
                                  │
                        frontend/ (React, read-only)
```

1. **Fuzzing** — `docker-compose.yml` runs one AFL++ master and three
   secondaries against the harness built by the root `Dockerfile`. All
   instances share `/data`, where AFL++ keeps its output directory and the
   seed corpus lives.
2. **Statistics** — every 15 minutes a cron job runs
   `triage/update_session_stats.py`, which parses `afl-whatsup` and appends a
   coverage/exec-count reading for the session and one reading per fuzzer
   instance (master and secondaries separately). Nothing is overwritten, so
   coverage can be plotted over time.
3. **Triage** — the same cron job runs CASR over new AFL++ crashes and feeds
   the reports to `triage/triage.py`, which classifies each crash, keys it on
   its crash site (file, line and column) so repeats of a known location are
   skipped, archives the crashing input and inserts the finding.
4. **Disclosure** — the API serves the data and the frontend renders it. A
   finding is created as `new` and `private`. Once it has been reported
   upstream it is switched to `reported` (with the report URL) and `public`;
   only then does the site show its stack trace, source context, sanitizer
   summary and PoC download. The frontend cannot change any of this.

## Repository layout

| Path | Purpose |
| --- | --- |
| `Dockerfile`, `docker-compose.yml` | Harness/fuzzer image and the fuzzer + database + API services |
| `api/` | FastAPI service exposing programs, targets, sessions, findings and PoC downloads ([README](api/README.md)) |
| `triage/` | Cron-driven collectors: coverage/instance statistics and CASR crash ingestion ([README](triage/README.md)) |
| `db/` | Numbered SQL migrations and the migration runner ([README](db/README.md)) |
| `frontend/` | React + Vite disclosure site ([README](frontend/README.md)) |
| `docs/` | [Codebase guide](docs/codebase.md) and diagrams (database schema, frontend structure) |
| `.github/workflows/deploy.yml` | Push-to-deploy to the fuzzing host |

## Data model

- **programs** → **targets**: the library under test and each fuzzed input
  format / harness.
- **sessions**: one fuzzing run of a target; carries the latest coverage and
  total executions.
- **coverage_history**: session-level coverage and exec readings over time.
- **fuzzer_instances**: per-instance readings (`fuzzer0` = master,
  `fuzzerN` = secondary) — coverage, execs/s, crashes saved — over time.
- **crashes**: one row per unique finding with severity, stack trace, source
  context, sanitizer summary, PoC path/hash, `status`, `visibility` and
  `report_url`.
- **schema_migrations**: applied migration versions.

## Running it

Requirements: Docker with the compose plugin, a `/data` directory on the host
for the shared volume, and Python 3 with `psycopg2` for the triage scripts.

```
# 1. database, API and fuzzers
export FUZZER_DB_PASSWORD=...        # also referenced by docker-compose.yml
docker compose up -d postgres api
python3 db/run_migrations.py          # DB_HOST/DB_PORT/FUZZER_DB_PASSWORD from env
docker compose up -d                  # start the fuzzers once a seed corpus is in /data

# 2. register what is being fuzzed
psql ... -c "INSERT INTO programs (name, repo_url) VALUES ('<program>', '<url>');"
psql ... -c "INSERT INTO targets (program_id, focus, harness_version) VALUES (1, '<FORMAT>', '<harness tag>');"

# 3. collect statistics and triage crashes every 15 minutes
*/15 * * * * /data/run_triage.sh      # calls update_session_stats.py and triage.py, see triage/README.md
```

The frontend is a static build (`frontend/`, `npm run build`) that talks to
the API over HTTP; see its README for local development.

## Deployment

Pushing to `main` triggers `.github/workflows/deploy.yml`, which connects to
the fuzzing host over SSH, pulls the repository, rebuilds the images and
recreates the API container. The fuzzer containers are intentionally left
running so an in-progress campaign is never interrupted by a deploy.

## Disclosure policy

Findings are held privately until they have been triaged and reported to the
maintainers of the affected project. The site never publishes technical detail
or a proof-of-concept for an unreported finding.

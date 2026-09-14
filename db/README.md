# db

Schema for the pipeline database, managed as numbered SQL migrations.

## Migrations

`migrations/NNN_name.sql` files are applied in numeric order by
`run_migrations.py`, which records each applied version in
`schema_migrations` and skips versions already present. The runner reads
`DB_HOST` (default `127.0.0.1`), `DB_PORT` (default `5432`) and
`FUZZER_DB_PASSWORD` from the environment:

```
DB_HOST=... DB_PORT=... FUZZER_DB_PASSWORD=... python3 db/run_migrations.py
```

| Version | Adds |
| --- | --- |
| 001 | `programs`, `targets`, `sessions`, `crashes`, `crash_targets` |
| 002 | `coverage_history` — session coverage/exec readings over time |
| 003 | `fuzzer_instances` — per-instance readings over time |
| 004 | `crashes.report_url` — link to the upstream report |
| 005 | `sessions.fuzzer_started_at` — AFL++ master start time, for restart detection |

To add a migration, create the next numbered file and run the runner; never
edit an applied migration.

## archive/

One-off maintenance scripts that were run once against production and are
kept for the record (dated in the file name). They are not meant to be run
again.

- `2026-09-13_retro_dedupe_fix.py` — moved stale PoC paths and collapsed
  duplicates created before load addresses were stripped from the hash.
- `2026-09-13_rehash_by_crash_site.py` — re-keyed the earliest finding per
  crash site when dedup switched to the crash location.
- `2026-09-13_delete_hidden_duplicates.py` — deleted the findings that
  repeated an earlier crash site, and their orphaned PoC files.

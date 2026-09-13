# triage

The cron wrapper and two scripts that turn the AFL++ output directory into
database rows. They run on the fuzzing host every 15 minutes and connect to
Postgres on `127.0.0.1:5432` with `FUZZER_DB_PASSWORD` from the environment.

## update_session_stats.py `<target_id>`

Runs `afl-whatsup` inside the master container and records:

- the session-level summary (coverage reached, total execs) — written to the
  target's latest `sessions` row **and** appended to `coverage_history`, so
  the history is never overwritten;
- one `fuzzer_instances` row per live instance (`fuzzer0` = master,
  `fuzzerN` = secondary) with its coverage, execs/s and crashes saved.
  Dead or remote instances are skipped.

If no session exists for the target one is created.

## triage.py `<casr_output_dir> <session_id>`

Ingests CASR `.casrep` reports produced from AFL++ crashes:

1. Keys the finding on its crash site (`CrashLine`, i.e. `file:line:col`;
   falls back to the address-stripped top stack frame), so every later crash
   at an already-recorded location is treated as a repeat.
2. Inserts the finding (severity, stack trace, source context, sanitizer
   summary, PoC size and SHA-256) with `ON CONFLICT (input_hash) DO NOTHING`,
   which silently drops those repeats.
3. Copies the crashing input to `<POC_ARCHIVE_ROOT>/<focus>/crash_NNNN.<focus>`
   (the focus comes from the session's target) and stores its path.

New findings start as `status = 'new'`, `visibility = 'private'`.

## run_triage.sh

The cron entry point. It picks the active target (newest `targets` row, or
`TARGET_ID` from the env file), runs `update_session_stats.py`, runs CASR
over the AFL++ crash directory in the fuzzer image, then runs `triage.py`
on the reports. Configuration comes from `/data/fuzzer-pipeline.env`
(`FUZZER_DB_PASSWORD` plus optional overrides listed at the top of the
script):

```
*/15 * * * * /home/opc/fuzzer-pipeline/triage/run_triage.sh
```

Both Python scripts accept `DB_HOST` / `DB_PORT` overrides (default
`127.0.0.1:5432`); `update_session_stats.py` also accepts
`AFL_MASTER_CONTAINER` and `AFL_OUTPUT`.

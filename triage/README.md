# triage

The cron wrapper and the scripts that turn the AFL++ output directory into
database rows. They run on the fuzzing host every 15 minutes and connect to
Postgres on `127.0.0.1:5432` with `FUZZER_DB_PASSWORD` from the environment.

## update_session_stats.py `<target_id>`

Runs `afl-whatsup` inside the master container and records:

- the session-level summary (coverage reached, total execs) — written to the
  target's latest `sessions` row **and** appended to `coverage_history`, so
  the history is never overwritten;
- one `fuzzer_instances` row per live instance (`fuzzer0` = master,
  `fuzzerN` = secondary) with its coverage, execs/s and crashes saved.
  Dead or remote instances are skipped. `afl-whatsup` prints `crashes saved
  N` only once an instance's count is nonzero, and `no crashes yet`
  otherwise — the parser must treat both as a live, parseable instance (the
  latter as zero), or every instance with no crashes yet reads as dead.

If no session exists for the target one is created.

The session follows the run: the master's `start_time` from `fuzzer_stats`
is kept in `sessions.fuzzer_started_at`. A different start on a later pass
means the fuzzers were restarted for the same target — the session's
`coverage_history` and `fuzzer_instances` rows are deleted and its clock
reset, its findings stay. If the master container is not running at all
(`docker inspect`), the script sets `ended_at` on the latest session, leaves
the readings in place (the site keeps showing the last run) and exits 0.

## triage.py `<casr_output_dir> <session_id>`

Ingests CASR `.casrep` reports produced from AFL++ crashes:

1. Resolves each report's `CrashLine` / `Stacktrace` with `symbolize.py`
   first, in place, when they're still raw addresses (see below) --
   everything after this step works on the resolved values.
2. Keys the finding on its crash site (`CrashLine`, i.e. `file:line:col`;
   falls back to the address-stripped top stack frame), so every later crash
   at an already-recorded location is treated as a repeat.
3. Inserts the finding (severity, stack trace, source context, sanitizer
   summary, PoC size and SHA-256) with `ON CONFLICT (input_hash) DO NOTHING`,
   which silently drops those repeats.
4. Copies the crashing input to `<POC_ARCHIVE_ROOT>/<focus>/crash_NNNN.<focus>`
   (the focus comes from the session's target) and stores its path.

New findings start as `status = 'new'`, `visibility = 'private'`.

## symbolize.py (library, not a cron entry point)

Under memory pressure (parallel CASR jobs + fuzzers) ASan can fail to fork
`llvm-symbolizer` at crash time (`WARNING: failed to fork (errno 12)`),
leaving `CrashLine` and the matching `Stacktrace` frame(s) as a raw
`<module>+0x<offset>` address instead of `file:line:col`. Besides making the
finding unreadable, this breaks dedup: the same bug resolves to the same
source line most of the time but not always, so one occurrence that hit the
fork failure gets ingested as a separate finding from the others.

`resolve_crash_site(crash_line, stacktrace, image, harness_path)` fixes this
offline, independent of runtime memory, by resolving the address itself with
`llvm-symbolizer` run inside `image` (a short-lived `docker run`, never
`docker exec` into the live fuzzer) -- but only once it has confirmed a
`BuildId` CASR embedded in the raw stack frames matches `harness_path`'s
actual Build ID inside that same `image` (`llvm-readelf -n` / `readelf -n`).
A mismatch (wrong or rebuilt binary) or any resolution failure leaves
`crash_line` / `stacktrace` unchanged. `llvm-symbolizer` itself is located at
runtime (`command -v llvm-symbolizer`, else the highest-numbered
`/usr/bin/llvm-symbolizer-N`), and every address the report needs resolved
(the `CrashLine` address plus every matching `Stacktrace` frame) is batched
into that one invocation.

Unit tests (no DB, no docker -- every `docker`/`llvm-symbolizer` call is
mocked): `python3 -m unittest discover -s triage/tests`.

## resymbolize_existing.py `--image IMAGE [--harness PATH] [--apply]`

One-off operator script applying the same fix to rows already in the
database (ingested before `triage.py` did this at insert time). Dry run by
default -- prints the harness Build ID found in `IMAGE`, then for every
`crashes` row whose `crash_line` is still a raw address: `id`, old `->` new
`crash_line`, and whether its embedded BuildId matched. `--apply` writes the
resolved `crash_line` / `stacktrace`. `IMAGE` is required and never defaulted
or looked up -- pass the exact image the crashes being fixed came from.

Only updates `crash_line` / `stacktrace`, never `input_hash`: two rows that
turn out to share a site after resolving can't collide on the column's
uniqueness constraint this way (the frontend already dedups by `crash_line`
for display), though a *new* crash landing on one of these corrected rows
after this runs would still get its own row, since that row's `input_hash`
was never recomputed. `triage.py`'s own fix doesn't have this gap, since it
resolves before computing `input_hash` in the first place.

Test only against a disposable database (see `CLAUDE.md`'s "Local testing"
rules) -- never run this against production from here.

## run_triage.sh

The cron entry point. It resolves `AFL_MASTER_CONTAINER`'s current image
(`docker inspect --format '{{.Image}}'`) into `CASR_IMAGE` -- falling back to
the `FUZZER_IMAGE` tag if that can't be resolved (logged either way) -- and
picks the active target (newest `targets` row, or `TARGET_ID` from the env
file), runs `update_session_stats.py`, runs CASR over the AFL++ crash
directory in `CASR_IMAGE`, then runs `triage.py` on the reports with that
same `CASR_IMAGE` exported for it to symbolize against. CASR and
`symbolize.py` must always run against the *same* image, master or fallback:
a report's embedded addresses and BuildId only ever match the binary CASR
actually reproduced the crash with, so symbolizing against any other image
means nothing would ever resolve. Configuration comes from the repo-root
`.env` (the same file `docker compose` reads; `FUZZER_DB_PASSWORD` plus
optional overrides listed at the top of the script and in `.env.example`):

```
*/15 * * * * /home/opc/fuzzer-pipeline/triage/run_triage.sh
```

Both Python scripts accept `DB_HOST` / `DB_PORT` overrides (default
`127.0.0.1:5432`); `update_session_stats.py` also accepts
`AFL_MASTER_CONTAINER` and `AFL_OUTPUT`; `triage.py` also accepts `HARNESS`
and `CASR_IMAGE` (both set by `run_triage.sh`) for offline symbolization.

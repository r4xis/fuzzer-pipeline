# Switching the fuzzing target

What to do when you start fuzzing a new input format (a new *target*) or a
new library (a new *program*). The API and the frontend need no changes: they
read programs, targets, sessions and findings from the database. The
statistics collector and the crash triage pick up the **newest target row**
automatically, and the PoC archive directory follows the target's `focus`.

## What is target-specific

| Layer | Target-specific? | Where |
| --- | --- | --- |
| Harness source and instrumented build | yes | `harness/`, `Dockerfile` |
| Seed corpus and AFL++ command line | yes | `docker-compose.yml` (`-i /data/<seeds>`) |
| AFL++ output directory | per campaign | `/data/afl-output` |
| Program / target registration | data | `programs`, `targets` tables |
| Stats collector, triage, PoC archive | no — follow the DB | `triage/` |
| API, frontend | no | `api/`, `frontend/` |

## Step by step

### 1. Prepare the harness and image

- Put the new harness under `harness/` and point the `COPY` / compile lines
  in the root `Dockerfile` at it. If the library itself changes, update the
  clone/build steps in the same file.
- Put the seed corpus under `/data/<name>` on the host and set the `-i`
  path in every `fuzzer*` service of `docker-compose.yml`.

### 2. Stop the running campaign and keep its output apart

```
cd ~/fuzzer-pipeline
docker compose stop fuzzer0 fuzzer1 fuzzer2 fuzzer3
sudo mv /data/afl-output /data/afl-output.<old-focus>.$(date +%F)
```

AFL++ output must not be shared between campaigns: crash files of the old
target would otherwise be triaged into the new target's session.

### 3. Register the target

If the library is new, add the program first; then add the target. The
newest `targets` row becomes the active one at the next cron run.

```
docker exec -it fuzzer-db psql -U fuzzer -d fuzzer_db
INSERT INTO programs (name, repo_url) VALUES ('<program>', '<repository url>');   -- only for a new library
INSERT INTO targets (program_id, focus, harness_version)
VALUES ((SELECT id FROM programs WHERE name = '<program>'), '<FOCUS>', '<harness tag>');
```

`focus` is the format name shown on the site (for example `VGM`); its
lower-case form names the PoC archive directory (`/data/poc_archive/vgm/`)
and the extension of archived inputs. `harness_version` is a free-form tag
for your own bookkeeping and is not shown on the site.

### 4. Build and start

```
docker compose build
docker compose up -d
```

Committing and pushing the harness/compose changes also rebuilds the images
on the host through the deploy workflow, but starting the fuzzers is a
manual step by design.

### 5. Check the first cron run (within 15 minutes)

```
tail -n 40 /data/triage.log                    # "Active target: <id>", stats parsed
curl -s http://127.0.0.1:8000/targets           # new target has latest_session_id
ls /data/poc_archive/<focus>/                   # appears once the first crash is triaged
```

The site shows the new target in the sidebar and index immediately after
step 3; coverage, instances and the LIVE indicator appear after the first
cron run.

## Reporting a finding

Findings are created as `new` / `private`. When a finding has been reported
upstream, publish it:

```
UPDATE crashes
SET status = 'reported', visibility = 'public', report_url = '<issue url>'
WHERE id = <finding id>;
```

The site then unlocks its stack trace, source context, sanitizer summary
and PoC download.

## Host configuration

The cron job runs `triage/run_triage.sh` from the repository checkout:

```
*/15 * * * * /home/opc/fuzzer-pipeline/triage/run_triage.sh
```

It reads `/data/fuzzer-pipeline.env` (not in the repository, mode 600):

```
FUZZER_DB_PASSWORD=...
# optional overrides
# TARGET_ID=3            pin a target instead of using the newest row
# AFL_OUTPUT=/data/afl-output
# POC_ARCHIVE_ROOT=/data/poc_archive
# FUZZER_IMAGE=fuzzer-pipeline-fuzzer0
# HARNESS=/fuzzing/harness
```

## Going back to an earlier target

Either register it again as a new target row (a fresh session and clean
counts), or pin it with `TARGET_ID=<id>` in the env file to keep appending to
its existing session.

# Crash Disclosure frontend

React + Vite single-page app for browsing fuzzing findings served by the
FastAPI backend in `../api`. It is a disclosure bulletin, not a dashboard:
program → target → findings, with technical detail (stack trace, source
context, sanitizer output, PoC download) shown only for findings whose
status is `reported`.

## Running locally

```
npm install
npm run dev          # http://127.0.0.1:5173
```

The app talks to the API at `http://localhost:8000` by default. Override with
`VITE_API_BASE` (e.g. in `.env.local`):

```
VITE_API_BASE=http://127.0.0.1:8000
```

The API itself needs a reachable Postgres. When running `api/main.py` on a
workstation against the production database, open an SSH tunnel first and
point the API at it:

```
ssh -i <key> -N -f -L 5433:127.0.0.1:5432 opc@<host>
cd ../api && DB_HOST=localhost DB_PORT=5433 FUZZER_DB_PASSWORD=<password> uvicorn main:app --reload --port 8000
```

If the API is up but its database is not, every data endpoint returns 500 and
the UI shows a "Backend unavailable" notice that retries automatically.

## Scripts

- `npm run dev` — dev server with HMR
- `npm run build` — production build to `dist/`
- `npm run lint` — ESLint (includes the React Compiler hook rules)
- `npm run preview` — serve the production build

## Layout

```
src/
  App.jsx                 shell, selection state, top-level data hooks
  hooks.js                polling, live/closed heuristic, crash-count watcher
  format.js               number/date formatting helpers
  api/client.js           thin fetch wrappers over the backend endpoints
  components/
    Header.jsx            title, LIVE/CLOSED indicator, social links, mobile nav toggle
    Sidebar.jsx           persistent program → target tree
    Footer.jsx            project description and links
    SignalTrace.jsx       oscilloscope line showing the selected instance's crashes-saved
                          history (master by default); spikes when a new finding appears
    IndexView.jsx         landing view listing programs and targets
    TargetList.jsx        targets of one program
    TargetOverview.jsx    coverage chart, fuzzer instances, findings for a target
    CoverageChart.jsx     coverage over time, y-axis scaled to the session's own range
    InstanceTable.jsx     fuzzer0 (master) / fuzzerN (slave) readings
    CrashList.jsx         findings with All / Reported tabs
    CrashDetail.jsx       finding detail, gated on status === "reported"
    ApiUnreachable.jsx    backend-down notice with retry
```

## Behaviour notes

- **LIVE / CLOSED** is inferred: if the newest `recorded_at` for the selected
  target's session (from `/sessions/{id}/history` or `/instances`) is less
  than 20 minutes old at the time of the last poll, the target is LIVE.
  Session data is polled every 5 minutes; readings themselves are produced
  every 15 minutes by the pipeline's cron job.
- **Signal trace spike**: the crash count for the selected target is polled
  every 45 seconds; if it increased since the previous poll, the trace flashes
  a transient and the findings list refreshes.
- **Target → session mapping** comes from `latest_session_id` on the
  `/targets` response. That field is added by `api/main.py` (a subquery for
  the target's most recent session); without it, coverage, instances and the
  live indicator fall back to a "no session" state.
- **Read-only**: the UI never changes finding status or visibility. Those are
  set on the backend; `status` is `new` until a finding has been reported,
  then `reported`, at which point its `report_url` is shown and the technical
  detail unlocks.

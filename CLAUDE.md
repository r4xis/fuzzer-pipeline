# Rules for coding agents working in this repo

## Never connect to production

Don't SSH to the fuzzing host, open a tunnel to it, or otherwise reach the
production database or API from an agent session — not even read-only, not
even to "quickly check" something. That access is the human operator's,
over their own SSH key, on their own machine. If a task seems to need it,
stop and say so instead of finding a way to do it yourself.

As a hard backstop, treat these ports as off-limits for anything an agent
starts locally, because they are the production-adjacent ports in normal
use on this project (prod Postgres over a tunnel, the API, and the
documented admin-access tunnel/port — see `docs/codebase.md`'s "Admin
access" section):

- `5432` (Postgres)
- `8000` (API)
- `8001` (the documented admin-access API port)
- `15432` (the documented admin-access tunnel's local port)

## Local testing

Local tests run against a disposable database (a throwaway `postgres`
container, migrated fresh, torn down after) — never against the production
database, never against any database the human is using interactively.

Pick a free, non-default, non-reserved port explicitly (not one of the
ports above, not a framework's default) for anything you start — a test
API, a test DB. Before sending it any request, **verify the process you
started actually bound that port** (e.g. check that something is listening
and that it's your PID, such as `ss -ltnp | grep ":<port> "`). If the port
was already taken, fail loudly and pick another port or stop — don't let a
failed bind pass silently and send requests to whatever was already
listening there. That exact mistake has happened in this repo before (an
agent's test uvicorn failed to bind port 8000 because the operator's own
admin instance — tunnelled to production — already held it, and the
agent's subsequent requests silently went to that live production-backed
instance instead).

Clean up everything you start: kill processes you launched, remove
containers and temp files, and leave the working tree as you found it
(revert any change made only to produce a test failure, such as deliberately
breaking an allowlist to prove a check catches it).

## Browser automation stays on localhost

Browser automation (claude-in-chrome or any other) may only navigate to
`localhost` / `127.0.0.1` URLs that you started yourself — never to an
external site, and never to GitHub, Cloudflare, Oracle Cloud, or any other
console. The browser carries the operator's own logged-in sessions, so
navigating it elsewhere acts as them. If a task needs anything outside
localhost, stop and say so instead of finding a way to do it yourself.

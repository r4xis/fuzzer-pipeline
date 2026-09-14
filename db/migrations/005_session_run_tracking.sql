-- The AFL++ master's start_time (from fuzzer_stats) for the run a session
-- describes. The collector compares it with the running master on every
-- pass: a different value means the fuzzers were restarted for the same
-- target, and the session's readings are reset while its findings are kept.
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS fuzzer_started_at TIMESTAMPTZ;

CREATE TABLE coverage_history (
    id              SERIAL PRIMARY KEY,
    session_id      INT REFERENCES sessions(id),
    recorded_at     TIMESTAMPTZ DEFAULT now(),
    coverage_pct    NUMERIC(5,2),
    total_execs     BIGINT
);

CREATE INDEX idx_coverage_history_session ON coverage_history(session_id, recorded_at);

CREATE TABLE fuzzer_instances (
    id              SERIAL PRIMARY KEY,
    session_id      INT REFERENCES sessions(id),
    instance_name   TEXT NOT NULL,
    coverage_pct    NUMERIC(5,2),
    execs_per_sec   NUMERIC(10,2),
    crashes_saved   INT,
    recorded_at     TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_fuzzer_instances_session ON fuzzer_instances(session_id, recorded_at);

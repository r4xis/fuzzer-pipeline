CREATE TABLE programs (
    id          SERIAL PRIMARY KEY,
    name        TEXT NOT NULL UNIQUE,
    repo_url    TEXT,
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE targets (
    id              SERIAL PRIMARY KEY,
    program_id      INT REFERENCES programs(id),
    focus           TEXT NOT NULL,
    commit_hash     TEXT,
    harness_version TEXT,
    created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE sessions (
    id              SERIAL PRIMARY KEY,
    target_id       INT REFERENCES targets(id),
    started_at      TIMESTAMPTZ,
    ended_at        TIMESTAMPTZ,
    seed_count      INT,
    total_execs     BIGINT,
    coverage_pct    NUMERIC(5,2)
);

CREATE TABLE crashes (
    id                SERIAL PRIMARY KEY,
    session_id        INT REFERENCES sessions(id),

    crash_line        TEXT,
    severity_type     TEXT,
    severity_desc     TEXT,
    severity_explain  TEXT,
    stacktrace        TEXT[],
    asan_summary      TEXT,

    input_hash        TEXT UNIQUE,
    afl_crash_id      TEXT,

    poc_file_path     TEXT NOT NULL,
    poc_file_size     INT,
    poc_file_sha256   TEXT,

    visibility        TEXT DEFAULT 'private',
    status            TEXT DEFAULT 'new',
    discovered_at     TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE crash_targets (
    crash_id    INT REFERENCES crashes(id),
    target_id   INT REFERENCES targets(id),
    PRIMARY KEY (crash_id, target_id)
);

CREATE INDEX idx_crashes_visibility ON crashes(visibility);
CREATE INDEX idx_crashes_status ON crashes(status);
CREATE INDEX idx_crashes_input_hash ON crashes(input_hash);

ALTER TABLE crashes ADD COLUMN IF NOT EXISTS source_context TEXT[];

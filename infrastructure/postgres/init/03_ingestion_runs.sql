CREATE TABLE IF NOT EXISTS ingestion_runs (
    run_id                BIGSERIAL PRIMARY KEY,
    source                TEXT NOT NULL,
    query_name            TEXT NOT NULL,
    search                TEXT,
    api_filter            TEXT,
    window_start          DATE,
    window_end            DATE,
    started_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at           TIMESTAMPTZ,
    status                TEXT NOT NULL DEFAULT 'running'
                          CHECK (status IN ('running', 'success', 'failed', 'test')),
    pages                 INT NOT NULL DEFAULT 0,
    works_fetched         INT NOT NULL DEFAULT 0,
    max_publication_date  DATE,
    error                 TEXT
);

CREATE INDEX IF NOT EXISTS idx_runs_lookup
    ON ingestion_runs (source, query_name, window_start, status);

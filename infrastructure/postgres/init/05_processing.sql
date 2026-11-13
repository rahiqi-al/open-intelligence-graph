ALTER TABLE papers ADD COLUMN IF NOT EXISTS title_norm TEXT;
ALTER TABLE papers ADD COLUMN IF NOT EXISTS author_names TEXT[];
CREATE INDEX IF NOT EXISTS idx_papers_title_norm ON papers (title_norm);

CREATE TABLE IF NOT EXISTS processed_files (
    object_key        TEXT PRIMARY KEY,
    source            TEXT NOT NULL,
    records_total     INT NOT NULL DEFAULT 0,
    records_rejected  INT NOT NULL DEFAULT 0,
    processed_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS rejected_records (
    rejected_id  BIGSERIAL PRIMARY KEY,
    source       TEXT NOT NULL,
    object_key   TEXT NOT NULL,
    source_id    TEXT,
    title        TEXT,
    reason       TEXT NOT NULL,
    details      TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_rejected_reason ON rejected_records (reason);

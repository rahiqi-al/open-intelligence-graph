CREATE TABLE IF NOT EXISTS paper_extractions (
    paper_id       BIGINT PRIMARY KEY REFERENCES papers(paper_id) ON DELETE CASCADE,
    status         TEXT NOT NULL CHECK (status IN ('done', 'failed')),
    model          TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    entities       JSONB,
    relations      JSONB,
    n_entities     INT,
    n_relations    INT,
    error          TEXT,
    seconds        REAL,
    extracted_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

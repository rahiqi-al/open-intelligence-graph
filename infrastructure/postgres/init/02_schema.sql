-- Open Intelligence Graph: PostgreSQL schema (source of truth for metadata)

CREATE TABLE IF NOT EXISTS institutions (
    institution_id  BIGSERIAL PRIMARY KEY,
    openalex_id     TEXT UNIQUE,
    name            TEXT NOT NULL,
    country_code    TEXT,
    type            TEXT
);

CREATE TABLE IF NOT EXISTS authors (
    author_id       BIGSERIAL PRIMARY KEY,
    openalex_id     TEXT UNIQUE,
    orcid           TEXT,
    display_name    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS topics (
    topic_id        BIGSERIAL PRIMARY KEY,
    openalex_id     TEXT UNIQUE,
    name            TEXT NOT NULL,
    subfield        TEXT,
    field           TEXT,
    domain          TEXT
);

CREATE TABLE IF NOT EXISTS papers (
    paper_id          BIGSERIAL PRIMARY KEY,
    openalex_id       TEXT UNIQUE,
    doi               TEXT UNIQUE,
    arxiv_id          TEXT UNIQUE,
    title             TEXT NOT NULL,
    abstract          TEXT NOT NULL,
    publication_year  INT,
    publication_date  DATE,
    type              TEXT,
    language          TEXT,
    cited_by_count    INT NOT NULL DEFAULT 0,
    is_open_access    BOOLEAN,
    pdf_url           TEXT,
    has_full_text     BOOLEAN NOT NULL DEFAULT FALSE,
    access_level      TEXT NOT NULL DEFAULT 'public'
                      CHECK (access_level IN ('public', 'restricted')),
    source            TEXT NOT NULL DEFAULT 'openalex',
    ingested_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS paper_authors (
    paper_id         BIGINT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    author_id        BIGINT NOT NULL REFERENCES authors(author_id) ON DELETE CASCADE,
    author_position  INT,
    PRIMARY KEY (paper_id, author_id)
);

CREATE TABLE IF NOT EXISTS author_institutions (
    author_id        BIGINT NOT NULL REFERENCES authors(author_id) ON DELETE CASCADE,
    institution_id   BIGINT NOT NULL REFERENCES institutions(institution_id) ON DELETE CASCADE,
    PRIMARY KEY (author_id, institution_id)
);

CREATE TABLE IF NOT EXISTS paper_topics (
    paper_id    BIGINT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    topic_id    BIGINT NOT NULL REFERENCES topics(topic_id) ON DELETE CASCADE,
    score       REAL,
    is_primary  BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (paper_id, topic_id)
);

-- Cited works are stored by OpenAlex ID, even if the cited paper is not in our database yet.
CREATE TABLE IF NOT EXISTS paper_references (
    citing_paper_id    BIGINT NOT NULL REFERENCES papers(paper_id) ON DELETE CASCADE,
    cited_openalex_id  TEXT NOT NULL,
    cited_paper_id     BIGINT REFERENCES papers(paper_id) ON DELETE SET NULL,
    PRIMARY KEY (citing_paper_id, cited_openalex_id)
);

-- Used by RBAC (Day 16)
CREATE TABLE IF NOT EXISTS users (
    user_id        BIGSERIAL PRIMARY KEY,
    email          TEXT NOT NULL UNIQUE,
    password_hash  TEXT NOT NULL,
    role           TEXT NOT NULL DEFAULT 'viewer'
                   CHECK (role IN ('admin', 'researcher', 'viewer')),
    created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_papers_year  ON papers(publication_year);
CREATE INDEX IF NOT EXISTS idx_papers_type  ON papers(type);
CREATE INDEX IF NOT EXISTS idx_refs_cited   ON paper_references(cited_openalex_id);
CREATE INDEX IF NOT EXISTS idx_pt_topic     ON paper_topics(topic_id);

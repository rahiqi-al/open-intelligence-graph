ALTER TABLE papers ADD COLUMN IF NOT EXISTS embed_level TEXT CHECK (embed_level IN ('abstract', 'full'));
ALTER TABLE papers ADD COLUMN IF NOT EXISTS chunk_count INT;
ALTER TABLE papers ADD COLUMN IF NOT EXISTS embedded_at TIMESTAMPTZ;
ALTER TABLE papers ADD COLUMN IF NOT EXISTS embed_error TEXT;
CREATE INDEX IF NOT EXISTS idx_papers_embedded ON papers (embedded_at, embed_level);

ALTER TABLE papers ADD COLUMN IF NOT EXISTS pdf_status TEXT NOT NULL DEFAULT 'pending'
    CHECK (pdf_status IN ('pending', 'downloaded', 'failed'));
ALTER TABLE papers ADD COLUMN IF NOT EXISTS pdf_key TEXT;
ALTER TABLE papers ADD COLUMN IF NOT EXISTS pdf_bytes BIGINT;
ALTER TABLE papers ADD COLUMN IF NOT EXISTS pdf_sha256 TEXT;
ALTER TABLE papers ADD COLUMN IF NOT EXISTS pdf_error TEXT;
ALTER TABLE papers ADD COLUMN IF NOT EXISTS pdf_attempts INT NOT NULL DEFAULT 0;
ALTER TABLE papers ADD COLUMN IF NOT EXISTS pdf_downloaded_at TIMESTAMPTZ;
-- text_status: 'extracted' means "the text can be extracted from this PDF" (checked in memory, nothing stored)
ALTER TABLE papers ADD COLUMN IF NOT EXISTS text_status TEXT NOT NULL DEFAULT 'pending'
    CHECK (text_status IN ('pending', 'extracted', 'failed'));
ALTER TABLE papers ADD COLUMN IF NOT EXISTS page_count INT;
ALTER TABLE papers ADD COLUMN IF NOT EXISTS text_chars INT;
ALTER TABLE papers ADD COLUMN IF NOT EXISTS text_error TEXT;
ALTER TABLE papers DROP COLUMN IF EXISTS text_key;
CREATE INDEX IF NOT EXISTS idx_papers_pdf_status ON papers (pdf_status, text_status);

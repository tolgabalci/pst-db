CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS unaccent;

CREATE TABLE IF NOT EXISTS import_jobs (
  id uuid PRIMARY KEY,
  source_filename text NOT NULL,
  source_path text NOT NULL,
  file_size bigint NOT NULL DEFAULT 0,
  sha256 text,
  status text NOT NULL DEFAULT 'queued',
  processed_count integer NOT NULL DEFAULT 0,
  inserted_count integer NOT NULL DEFAULT 0,
  duplicate_count integer NOT NULL DEFAULT 0,
  attachment_count integer NOT NULL DEFAULT 0,
  semantic_indexed_count integer NOT NULL DEFAULT 0,
  error_count integer NOT NULL DEFAULT 0,
  last_error text,
  created_at timestamptz NOT NULL DEFAULT now(),
  started_at timestamptz,
  finished_at timestamptz
);

CREATE TABLE IF NOT EXISTS import_errors (
  id bigserial PRIMARY KEY,
  job_id uuid REFERENCES import_jobs(id) ON DELETE CASCADE,
  item_ref text,
  stage text NOT NULL,
  message text NOT NULL,
  details jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS emails (
  id uuid PRIMARY KEY,
  content_hash text NOT NULL UNIQUE,
  message_id text,
  subject text NOT NULL DEFAULT '',
  sender_name text,
  sender_email text,
  sent_at timestamptz,
  received_at timestamptz,
  body_text text NOT NULL DEFAULT '',
  body_html text,
  has_attachments boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS email_recipients (
  id bigserial PRIMARY KEY,
  email_id uuid NOT NULL REFERENCES emails(id) ON DELETE CASCADE,
  kind text NOT NULL,
  name text,
  email text
);

CREATE TABLE IF NOT EXISTS email_occurrences (
  id bigserial PRIMARY KEY,
  email_id uuid NOT NULL REFERENCES emails(id) ON DELETE CASCADE,
  job_id uuid REFERENCES import_jobs(id) ON DELETE SET NULL,
  pst_path text NOT NULL,
  folder_path text,
  entry_id text,
  imported_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(email_id, pst_path, folder_path, entry_id)
);

CREATE TABLE IF NOT EXISTS attachment_blobs (
  id uuid PRIMARY KEY,
  content_hash text NOT NULL UNIQUE,
  storage_path text NOT NULL,
  size_bytes bigint NOT NULL DEFAULT 0,
  mime_type text,
  extracted_text text,
  extraction_status text NOT NULL DEFAULT 'pending',
  extraction_error text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS email_attachments (
  id uuid PRIMARY KEY,
  email_id uuid NOT NULL REFERENCES emails(id) ON DELETE CASCADE,
  blob_id uuid NOT NULL REFERENCES attachment_blobs(id) ON DELETE RESTRICT,
  filename text NOT NULL DEFAULT 'attachment',
  content_id text,
  disposition text,
  ordinal integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS search_documents (
  id uuid PRIMARY KEY,
  email_id uuid NOT NULL REFERENCES emails(id) ON DELETE CASCADE,
  attachment_id uuid REFERENCES email_attachments(id) ON DELETE CASCADE,
  source_type text NOT NULL,
  title text NOT NULL DEFAULT '',
  chunk_index integer NOT NULL DEFAULT 0,
  content text NOT NULL DEFAULT '',
  weighted_tsv tsvector GENERATED ALWAYS AS (
    setweight(to_tsvector('english', coalesce(title, '')), 'A') ||
    setweight(to_tsvector('english', coalesce(content, '')), 'B')
  ) STORED,
  embedding vector(768),
  embedding_status text NOT NULL DEFAULT 'pending',
  embedding_error text,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE(email_id, attachment_id, source_type, chunk_index)
);

CREATE TABLE IF NOT EXISTS email_flags (
  email_id uuid PRIMARY KEY REFERENCES emails(id) ON DELETE CASCADE,
  is_favorite boolean NOT NULL DEFAULT false,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS user_notes (
  email_id uuid PRIMARY KEY REFERENCES emails(id) ON DELETE CASCADE,
  note text NOT NULL DEFAULT '',
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_import_jobs_status_created ON import_jobs(status, created_at);
CREATE INDEX IF NOT EXISTS idx_import_errors_job ON import_errors(job_id, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_emails_sender_email ON emails(lower(sender_email));
CREATE INDEX IF NOT EXISTS idx_emails_sent_at ON emails(sent_at DESC NULLS LAST);
CREATE INDEX IF NOT EXISTS idx_emails_subject_trgm ON emails USING gin(subject gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_recipients_email ON email_recipients(lower(email));
CREATE INDEX IF NOT EXISTS idx_occurrences_email ON email_occurrences(email_id);
CREATE INDEX IF NOT EXISTS idx_email_attachments_email ON email_attachments(email_id);
CREATE INDEX IF NOT EXISTS idx_email_attachments_filename_trgm ON email_attachments USING gin(filename gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_search_documents_email ON search_documents(email_id);
CREATE INDEX IF NOT EXISTS idx_search_documents_tsv ON search_documents USING gin(weighted_tsv);
CREATE INDEX IF NOT EXISTS idx_search_documents_embedding_hnsw ON search_documents USING hnsw (embedding vector_cosine_ops) WHERE embedding IS NOT NULL;


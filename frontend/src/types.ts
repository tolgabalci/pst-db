export type SearchMode = "all" | "keyword" | "semantic";

export interface AppSettings {
  search_result_cache_entries: number;
  search_result_cache_ttl_seconds: number;
  query_embedding_cache_entries: number;
  query_embedding_cache_ttl_seconds: number;
  folder_list_cache_entries: number;
  folder_list_cache_ttl_seconds: number;
  import_status_cache_entries: number;
  import_status_cache_ttl_seconds: number;
  email_detail_cache_entries: number;
  attachment_metadata_cache_entries: number;
  attachment_preview_cache_max_age_seconds: number;
}

export interface AttachmentSummary {
  id: string;
  filename: string;
  mime_type: string | null;
  size_bytes: number;
}

export interface SearchResult {
  id: string;
  subject: string;
  sender_name: string | null;
  sender_email: string | null;
  sent_at: string | null;
  received_at: string | null;
  has_attachments: boolean;
  is_favorite: boolean;
  keyword_score: number;
  semantic_score: number;
  score: number;
  snippet: string;
  attachments: AttachmentSummary[];
  match_reasons: string[];
}

export interface SearchResponse {
  results: SearchResult[];
  total: number;
  semantic_error?: string | null;
}

export interface MailboxFolder {
  folder_path: string;
  email_count: number;
}

export interface EmailDetail {
  id: string;
  message_id: string | null;
  subject: string;
  sender_name: string | null;
  sender_email: string | null;
  sent_at: string | null;
  received_at: string | null;
  body_text: string;
  body_html: string | null;
  has_attachments: boolean;
  is_favorite: boolean;
  note: string;
  recipients: Array<{ kind: string; name: string | null; email: string | null }>;
  occurrences: Array<{ pst_path: string; folder_path: string | null; entry_id: string | null; imported_at: string }>;
}

export interface AttachmentDetail extends AttachmentSummary {
  content_id: string | null;
  disposition: string | null;
  ordinal: number;
  content_hash: string;
  extraction_status: string;
  extraction_error: string | null;
  extracted_text_length: number;
}

export interface ImportFile {
  filename: string;
  source_path: string;
  relative_path: string;
  file_size: number;
  modified_at: number;
}

export interface ImportJob {
  id: string;
  source_filename: string;
  source_path: string;
  file_size: number;
  sha256: string | null;
  status: string;
  processed_count: number;
  inserted_count: number;
  duplicate_count: number;
  attachment_count: number;
  semantic_indexed_count: number;
  error_count: number;
  last_error: string | null;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
}

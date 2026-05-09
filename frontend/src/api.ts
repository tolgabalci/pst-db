import type {
  AttachmentDetail,
  EmailDetail,
  ImportFile,
  ImportJob,
  SearchMode,
  SearchResponse
} from "./types";

export const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

interface SearchParams {
  q: string;
  mode: SearchMode;
  author?: string;
  recipient?: string;
  subject?: string;
  attachmentFilename?: string;
  dateFrom?: string;
  dateTo?: string;
  hasAttachments?: boolean;
  favorite?: boolean;
  limit: number;
  offset: number;
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(options?.headers || {}) },
    ...options
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(body.detail || response.statusText);
  }
  return response.json() as Promise<T>;
}

export async function searchEmails(params: SearchParams): Promise<SearchResponse> {
  const query = new URLSearchParams();
  query.set("q", params.q);
  query.set("mode", params.mode);
  query.set("limit", String(params.limit));
  query.set("offset", String(params.offset));
  if (params.author) query.set("author", params.author);
  if (params.recipient) query.set("recipient", params.recipient);
  if (params.subject) query.set("subject", params.subject);
  if (params.attachmentFilename) query.set("attachment_filename", params.attachmentFilename);
  if (params.dateFrom) query.set("date_from", params.dateFrom);
  if (params.dateTo) query.set("date_to", params.dateTo);
  if (params.hasAttachments !== undefined) query.set("has_attachments", String(params.hasAttachments));
  if (params.favorite !== undefined) query.set("favorite", String(params.favorite));
  return request<SearchResponse>(`/api/search?${query.toString()}`);
}

export function getEmail(emailId: string): Promise<EmailDetail> {
  return request<EmailDetail>(`/api/emails/${emailId}`);
}

export function getEmailAttachments(emailId: string): Promise<AttachmentDetail[]> {
  return request<AttachmentDetail[]>(`/api/emails/${emailId}/attachments`);
}

export function setFavorite(emailId: string, isFavorite: boolean): Promise<{ is_favorite: boolean }> {
  return request(`/api/emails/${emailId}/favorite`, {
    method: "PATCH",
    body: JSON.stringify({ is_favorite: isFavorite })
  });
}

export function saveNote(emailId: string, note: string): Promise<{ note: string }> {
  return request(`/api/emails/${emailId}/note`, {
    method: "PUT",
    body: JSON.stringify({ note })
  });
}

export function scanImports(): Promise<{ files: ImportFile[] }> {
  return request("/api/imports/scan", { method: "POST" });
}

export function listImports(): Promise<ImportJob[]> {
  return request("/api/imports");
}

export function createImport(sourcePath: string): Promise<ImportJob> {
  return request("/api/imports", {
    method: "POST",
    body: JSON.stringify({ source_path: sourcePath })
  });
}

export const attachmentPreviewUrl = (id: string) => `${API_BASE}/api/attachments/${id}/preview`;
export const attachmentDownloadUrl = (id: string) => `${API_BASE}/api/attachments/${id}/download`;

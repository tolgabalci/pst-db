import type {
  AppSettings,
  AttachmentDetail,
  EmailDetail,
  ImportFile,
  ImportJob,
  MailboxFolder,
  SearchMode,
  SearchResponse
} from "./types";

export const API_BASE = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export const DEFAULT_APP_SETTINGS: AppSettings = {
  search_result_cache_entries: 128,
  search_result_cache_ttl_seconds: 60,
  query_embedding_cache_entries: 512,
  query_embedding_cache_ttl_seconds: 3600,
  folder_list_cache_entries: 4,
  folder_list_cache_ttl_seconds: 30,
  import_status_cache_entries: 8,
  import_status_cache_ttl_seconds: 2,
  email_detail_cache_entries: 150,
  attachment_metadata_cache_entries: 150,
  attachment_preview_cache_max_age_seconds: 86400
};

type CacheRecord<T> = {
  expiresAt: number;
  value: T;
};

let cacheSettings = DEFAULT_APP_SETTINGS;
const emailDetailCache = new Map<string, CacheRecord<EmailDetail>>();
const attachmentMetadataCache = new Map<string, CacheRecord<AttachmentDetail[]>>();
const folderListCache = new Map<string, CacheRecord<MailboxFolder[]>>();
const importScanCache = new Map<string, CacheRecord<{ files: ImportFile[] }>>();
const importJobsCache = new Map<string, CacheRecord<ImportJob[]>>();

function getCached<T>(cache: Map<string, CacheRecord<T>>, key: string, maxEntries: number, ttlSeconds: number): T | null {
  if (maxEntries <= 0 || ttlSeconds <= 0) return null;
  const record = cache.get(key);
  if (!record) return null;
  if (record.expiresAt <= Date.now()) {
    cache.delete(key);
    return null;
  }
  cache.delete(key);
  cache.set(key, record);
  return record.value;
}

function setCached<T>(cache: Map<string, CacheRecord<T>>, key: string, value: T, maxEntries: number, ttlSeconds: number): void {
  if (maxEntries <= 0 || ttlSeconds <= 0) return;
  cache.set(key, { value, expiresAt: Date.now() + ttlSeconds * 1000 });
  while (cache.size > maxEntries) {
    const oldestKey = cache.keys().next().value;
    if (!oldestKey) break;
    cache.delete(oldestKey);
  }
}

export function applyClientCacheSettings(settings: AppSettings): void {
  cacheSettings = settings;
  clearClientCaches();
}

export function clearClientCaches(): void {
  emailDetailCache.clear();
  attachmentMetadataCache.clear();
  folderListCache.clear();
  importScanCache.clear();
  importJobsCache.clear();
}

interface SearchParams {
  q: string;
  mode: SearchMode;
  author?: string;
  recipient?: string;
  folders?: string[];
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
  if (params.folders) {
    if (params.folders.length === 0) {
      query.append("folders", "__no_selected_folders__");
    } else {
      params.folders.forEach((folder) => query.append("folders", folder));
    }
  }
  if (params.subject) query.set("subject", params.subject);
  if (params.attachmentFilename) query.set("attachment_filename", params.attachmentFilename);
  if (params.dateFrom) query.set("date_from", params.dateFrom);
  if (params.dateTo) query.set("date_to", params.dateTo);
  if (params.hasAttachments !== undefined) query.set("has_attachments", String(params.hasAttachments));
  if (params.favorite !== undefined) query.set("favorite", String(params.favorite));
  return request<SearchResponse>(`/api/search?${query.toString()}`);
}

export function listSearchFolders(): Promise<MailboxFolder[]> {
  const cached = getCached(
    folderListCache,
    "folders",
    cacheSettings.folder_list_cache_entries,
    cacheSettings.folder_list_cache_ttl_seconds
  );
  if (cached) return Promise.resolve(cached);
  return request<MailboxFolder[]>("/api/search/folders").then((folders) => {
    setCached(
      folderListCache,
      "folders",
      folders,
      cacheSettings.folder_list_cache_entries,
      cacheSettings.folder_list_cache_ttl_seconds
    );
    return folders;
  });
}

export function getEmail(emailId: string): Promise<EmailDetail> {
  const cached = getCached(emailDetailCache, emailId, cacheSettings.email_detail_cache_entries, 300);
  if (cached) return Promise.resolve(cached);
  return request<EmailDetail>(`/api/emails/${emailId}`).then((email) => {
    setCached(emailDetailCache, emailId, email, cacheSettings.email_detail_cache_entries, 300);
    return email;
  });
}

export function getEmailAttachments(emailId: string): Promise<AttachmentDetail[]> {
  const cached = getCached(attachmentMetadataCache, emailId, cacheSettings.attachment_metadata_cache_entries, 300);
  if (cached) return Promise.resolve(cached);
  return request<AttachmentDetail[]>(`/api/emails/${emailId}/attachments`).then((attachments) => {
    setCached(attachmentMetadataCache, emailId, attachments, cacheSettings.attachment_metadata_cache_entries, 300);
    return attachments;
  });
}

export function setFavorite(emailId: string, isFavorite: boolean): Promise<{ is_favorite: boolean }> {
  return request<{ is_favorite: boolean }>(`/api/emails/${emailId}/favorite`, {
    method: "PATCH",
    body: JSON.stringify({ is_favorite: isFavorite })
  }).then((response) => {
    emailDetailCache.delete(emailId);
    return response;
  });
}

export function saveNote(emailId: string, note: string): Promise<{ note: string }> {
  return request<{ note: string }>(`/api/emails/${emailId}/note`, {
    method: "PUT",
    body: JSON.stringify({ note })
  }).then((response) => {
    emailDetailCache.delete(emailId);
    return response;
  });
}

export function scanImports(): Promise<{ files: ImportFile[] }> {
  const cached = getCached(importScanCache, "scan", cacheSettings.import_status_cache_entries, cacheSettings.import_status_cache_ttl_seconds);
  if (cached) return Promise.resolve(cached);
  return request<{ files: ImportFile[] }>("/api/imports/scan", { method: "POST" }).then((response) => {
    setCached(importScanCache, "scan", response, cacheSettings.import_status_cache_entries, cacheSettings.import_status_cache_ttl_seconds);
    return response;
  });
}

export function listImports(): Promise<ImportJob[]> {
  const cached = getCached(importJobsCache, "jobs", cacheSettings.import_status_cache_entries, cacheSettings.import_status_cache_ttl_seconds);
  if (cached) return Promise.resolve(cached);
  return request<ImportJob[]>("/api/imports").then((jobs) => {
    setCached(importJobsCache, "jobs", jobs, cacheSettings.import_status_cache_entries, cacheSettings.import_status_cache_ttl_seconds);
    return jobs;
  });
}

export function createImport(sourcePath: string): Promise<ImportJob> {
  return request<ImportJob>("/api/imports", {
    method: "POST",
    body: JSON.stringify({ source_path: sourcePath })
  }).then((job) => {
    importScanCache.clear();
    importJobsCache.clear();
    folderListCache.clear();
    return job;
  });
}

export function getAppSettings(): Promise<AppSettings> {
  return request<AppSettings>("/api/settings");
}

export function updateAppSettings(settings: AppSettings): Promise<AppSettings> {
  return request<AppSettings>("/api/settings", {
    method: "PUT",
    body: JSON.stringify(settings)
  }).then((saved) => {
    applyClientCacheSettings(saved);
    return saved;
  });
}

export const attachmentPreviewUrl = (id: string) => `${API_BASE}/api/attachments/${id}/preview`;
export const attachmentDownloadUrl = (id: string) => `${API_BASE}/api/attachments/${id}/download`;

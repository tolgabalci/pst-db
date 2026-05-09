import {
  Archive,
  Calendar,
  CheckCircle2,
  Database,
  Download,
  FileText,
  Filter,
  FolderSync,
  Heart,
  Inbox,
  Loader2,
  Mail,
  Paperclip,
  RefreshCw,
  Save,
  Search,
  Star,
  UserRound,
  XCircle
} from "lucide-react";
import { FormEvent, KeyboardEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  API_BASE,
  attachmentDownloadUrl,
  attachmentPreviewUrl,
  createImport,
  getEmail,
  getEmailAttachments,
  listImports,
  saveNote,
  scanImports,
  searchEmails,
  setFavorite
} from "./api";
import type { AttachmentDetail, EmailDetail, ImportFile, ImportJob, SearchMode, SearchResult } from "./types";

const PAGE_SIZE = 50;
const THUMBNAIL_IMAGE_TYPES = new Set(["image/png", "image/jpeg", "image/gif", "image/webp", "image/bmp"]);

function formatDate(value: string | null | undefined): string {
  if (!value) return "No date";
  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short"
  }).format(new Date(value));
}

function formatBytes(value: number): string {
  if (value < 1024) return `${value} B`;
  const units = ["KB", "MB", "GB", "TB"];
  let size = value / 1024;
  let index = 0;
  while (size >= 1024 && index < units.length - 1) {
    size /= 1024;
    index += 1;
  }
  return `${size.toFixed(size >= 10 ? 1 : 2)} ${units[index]}`;
}

function titleCaseName(value: string): string {
  if (!value || value !== value.toUpperCase()) return value;
  return value.toLowerCase().replace(/\b[a-z]/g, (letter) => letter.toUpperCase());
}

function legacyExchangeName(value: string | null | undefined): string | null {
  if (!value || !value.startsWith("/")) return null;
  const cnMatch = value.match(/\/CN=RECIPIENTS\/CN=[^-\/]+-([^\/]+)$/i) || value.match(/\/CN=([^\/]+)$/i);
  if (!cnMatch) return null;
  return titleCaseName(cnMatch[1].replace(/[._]+/g, " ").trim());
}

function displayPerson(name: string | null | undefined, address: string | null | undefined): string {
  const cleanName = name?.trim();
  if (cleanName && !cleanName.startsWith("/")) return cleanName;
  const legacyFromAddress = legacyExchangeName(address);
  if (legacyFromAddress) return legacyFromAddress;
  const legacyFromName = legacyExchangeName(cleanName);
  if (legacyFromName) return legacyFromName;
  return address?.trim() || cleanName || "Unknown";
}

function displayRecipients(recipients: EmailDetail["recipients"]): string {
  if (!recipients.length) return "None";
  const groups = [
    ["To", recipients.filter((item) => item.kind === "to")],
    ["Cc", recipients.filter((item) => item.kind === "cc")],
    ["Bcc", recipients.filter((item) => item.kind === "bcc")]
  ] as const;
  const rendered = groups
    .filter(([, items]) => items.length > 0)
    .map(([label, items]) => `${label}: ${items.map((item) => displayPerson(item.name, item.email)).join(", ")}`);
  return rendered.join(" · ") || "None";
}

type ImageAttachmentLike = Pick<AttachmentDetail, "filename" | "mime_type"> &
  Partial<Pick<AttachmentDetail, "content_id" | "disposition">>;

function isThumbnailImage(attachment: ImageAttachmentLike): boolean {
  const mimeType = attachment.mime_type?.toLowerCase();
  return Boolean(mimeType && THUMBNAIL_IMAGE_TYPES.has(mimeType));
}

function isGenericImageName(attachment: ImageAttachmentLike): boolean {
  const filename = attachment.filename.trim().toLowerCase();
  return (
    isThumbnailImage(attachment) &&
    (/^attachedimage(?:\.\w+)?$/i.test(filename) ||
      /^image\d+\.(png|jpe?g|gif|webp|bmp)$/i.test(filename) ||
      /^(logo|signature|spacer|banner|divider|facebook|twitter|linkedin|instagram|youtube)[-_]?\d*\.(png|jpe?g|gif|webp|bmp)$/i.test(
        filename
      ))
  );
}

function isInlineImage(attachment: ImageAttachmentLike): boolean {
  return isThumbnailImage(attachment) && Boolean(attachment.content_id || attachment.disposition?.toLowerCase() === "inline");
}

function isClutterImageAttachment(attachment: ImageAttachmentLike): boolean {
  return isGenericImageName(attachment) || isInlineImage(attachment);
}

function isMeetingRequest(result: SearchResult): boolean {
  const subject = (result.subject || "")
    .normalize("NFD")
    .replace(/\p{Diacritic}/gu, "")
    .toLocaleLowerCase();
  if (
    /^(accepted|declined|tentative|canceled|cancelled|updated|rescheduled|proposed new time|new time proposed):/.test(subject)
  ) {
    return true;
  }
  return /\b(invitation|meeting|teams|llamada|reunion|recording|grabacion)\b/.test(subject) && /\bshared\b/.test(subject);
}

function statusIcon(status: string) {
  if (status === "completed") return <CheckCircle2 size={16} />;
  if (status === "failed") return <XCircle size={16} />;
  if (status === "running") return <Loader2 size={16} className="spin" />;
  return <Archive size={16} />;
}

function moveFocusToResult(list: HTMLDivElement | null, resultId: string) {
  const row = list?.querySelector<HTMLButtonElement>(`[data-result-id="${resultId}"]`);
  row?.focus({ preventScroll: true });
  row?.scrollIntoView({ block: "nearest" });
}

export function App() {
  const [tab, setTab] = useState<"search" | "imports">("search");
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<SearchMode>("all");
  const [author, setAuthor] = useState("");
  const [recipient, setRecipient] = useState("");
  const [subject, setSubject] = useState("");
  const [attachmentFilename, setAttachmentFilename] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [hasAttachments, setHasAttachments] = useState(false);
  const [favoriteOnly, setFavoriteOnly] = useState(false);
  const [offset, setOffset] = useState(0);
  const [results, setResults] = useState<SearchResult[]>([]);
  const [total, setTotal] = useState(0);
  const [semanticError, setSemanticError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [detail, setDetail] = useState<EmailDetail | null>(null);
  const [attachments, setAttachments] = useState<AttachmentDetail[]>([]);
  const [noteDraft, setNoteDraft] = useState("");
  const [noteSaving, setNoteSaving] = useState(false);
  const [loading, setLoading] = useState(false);
  const [detailLoading, setDetailLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const resultListRef = useRef<HTMLDivElement | null>(null);

  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;
  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const runSearch = useCallback(
    async (nextOffset = 0) => {
      setLoading(true);
      setError(null);
      setResults([]);
      setTotal(0);
      setSelectedId(null);
      setSemanticError(null);
      try {
        const response = await searchEmails({
          q: query,
          mode,
          author,
          recipient,
          subject,
          attachmentFilename,
          dateFrom: dateFrom ? new Date(dateFrom).toISOString() : undefined,
          dateTo: dateTo ? new Date(`${dateTo}T23:59:59`).toISOString() : undefined,
          hasAttachments: hasAttachments ? true : undefined,
          favorite: favoriteOnly ? true : undefined,
          limit: PAGE_SIZE,
          offset: nextOffset
        });
        setResults(response.results);
        setTotal(response.total);
        setSemanticError(response.semantic_error || null);
        setOffset(nextOffset);
        setSelectedId(response.results[0]?.id || null);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Search failed.");
        setResults([]);
        setTotal(0);
        setSelectedId(null);
      } finally {
        setLoading(false);
      }
    },
    [attachmentFilename, author, dateFrom, dateTo, favoriteOnly, hasAttachments, mode, query, recipient, subject]
  );

  useEffect(() => {
    void runSearch(0);
  }, []);

  useEffect(() => {
    if (!selectedId) {
      setDetail(null);
      setAttachments([]);
      setNoteDraft("");
      return;
    }
    setDetailLoading(true);
    Promise.all([getEmail(selectedId), getEmailAttachments(selectedId)])
      .then(([email, emailAttachments]) => {
        setDetail(email);
        setAttachments(emailAttachments);
        setNoteDraft(email.note || "");
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load email."))
      .finally(() => setDetailLoading(false));
  }, [selectedId]);

  const selectedResult = useMemo(() => results.find((result) => result.id === selectedId), [results, selectedId]);
  const selectedIndex = useMemo(() => results.findIndex((result) => result.id === selectedId), [results, selectedId]);
  const noteHasChanges = detail ? noteDraft !== (detail.note || "") : false;
  const visibleDetailAttachments = useMemo(
    () => attachments.filter((attachment) => !isClutterImageAttachment(attachment)),
    [attachments]
  );

  const handleResultListKeyDown = useCallback(
    (event: KeyboardEvent<HTMLDivElement>) => {
      if (results.length === 0) return;

      let nextIndex: number | null = null;
      if (event.key === "ArrowDown") {
        const currentIndex = selectedIndex >= 0 ? selectedIndex : -1;
        nextIndex = Math.min(results.length - 1, currentIndex + 1);
      } else if (event.key === "ArrowUp") {
        const currentIndex = selectedIndex >= 0 ? selectedIndex : results.length;
        nextIndex = Math.max(0, currentIndex - 1);
      } else if (event.ctrlKey && event.key === "Home") {
        nextIndex = 0;
      } else if (event.ctrlKey && event.key === "End") {
        nextIndex = results.length - 1;
      } else {
        return;
      }

      event.preventDefault();
      const nextResult = results[nextIndex];
      if (!nextResult || nextResult.id === selectedId) return;

      setSelectedId(nextResult.id);
      window.requestAnimationFrame(() => moveFocusToResult(resultListRef.current, nextResult.id));
    },
    [results, selectedId, selectedIndex]
  );

  async function submitSearch(event: FormEvent) {
    event.preventDefault();
    await runSearch(0);
  }

  async function toggleFavorite() {
    if (!detail) return;
    const next = !detail.is_favorite;
    await setFavorite(detail.id, next);
    setDetail({ ...detail, is_favorite: next });
    setResults((items) => items.map((item) => (item.id === detail.id ? { ...item, is_favorite: next } : item)));
  }

  async function persistNote() {
    if (!detail || !noteHasChanges || noteSaving) return;
    setNoteSaving(true);
    try {
      const saved = await saveNote(detail.id, noteDraft);
      setDetail({ ...detail, note: saved.note });
      setNoteDraft(saved.note);
    } finally {
      setNoteSaving(false);
    }
  }

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand">
          <Database size={22} />
          <span>Local PST Search</span>
        </div>
        <nav className="tabs" aria-label="Primary">
          <button className={tab === "search" ? "active" : ""} onClick={() => setTab("search")}>
            <Search size={16} />
            Search
          </button>
          <button className={tab === "imports" ? "active" : ""} onClick={() => setTab("imports")}>
            <FolderSync size={16} />
            Imports
          </button>
        </nav>
        <div className="api-pill">{API_BASE}</div>
      </header>

      {tab === "search" ? (
        <main className="search-layout">
          <section className="search-pane">
            <form className="search-form" onSubmit={submitSearch}>
              <div className="query-row">
                <Search size={18} />
                <input
                  value={query}
                  onChange={(event) => setQuery(event.target.value)}
                  placeholder="Search email and attachment content"
                />
                <button type="submit" className="primary" disabled={loading}>
                  {loading ? <Loader2 size={16} className="spin" /> : <Search size={16} />}
                  Run
                </button>
              </div>

              <div className="toolbar">
                <div className="segmented" aria-label="Search mode">
                  {(["all", "keyword", "semantic"] as SearchMode[]).map((item) => (
                    <button
                      key={item}
                      type="button"
                      className={mode === item ? "selected" : ""}
                      onClick={() => setMode(item)}
                    >
                      {item[0].toUpperCase() + item.slice(1)}
                    </button>
                  ))}
                </div>
                <label className="check">
                  <input type="checkbox" checked={hasAttachments} onChange={(event) => setHasAttachments(event.target.checked)} />
                  <Paperclip size={14} />
                  Has attachments
                </label>
                <label className="check">
                  <input type="checkbox" checked={favoriteOnly} onChange={(event) => setFavoriteOnly(event.target.checked)} />
                  <Star size={14} />
                  Favorites
                </label>
              </div>

              <div className="filters">
                <label>
                  <UserRound size={14} />
                  <input value={author} onChange={(event) => setAuthor(event.target.value)} placeholder="From" />
                </label>
                <label>
                  <UserRound size={14} />
                  <input value={recipient} onChange={(event) => setRecipient(event.target.value)} placeholder="To, Cc, or Bcc" />
                </label>
                <label>
                  <Mail size={14} />
                  <input value={subject} onChange={(event) => setSubject(event.target.value)} placeholder="Subject" />
                </label>
                <label>
                  <FileText size={14} />
                  <input
                    value={attachmentFilename}
                    onChange={(event) => setAttachmentFilename(event.target.value)}
                    placeholder="Attachment filename"
                  />
                </label>
                <label>
                  <Calendar size={14} />
                  <input type="date" value={dateFrom} onChange={(event) => setDateFrom(event.target.value)} />
                </label>
                <label>
                  <Calendar size={14} />
                  <input type="date" value={dateTo} onChange={(event) => setDateTo(event.target.value)} />
                </label>
              </div>
            </form>

            {error && <div className="notice error">{error}</div>}
            {semanticError && <div className="notice warn">Semantic search unavailable: {semanticError}</div>}

            <div className="result-header">
              <span>{loading ? "Searching..." : `${total.toLocaleString()} results`}</span>
              <span>
                Page {currentPage} of {totalPages}
              </span>
            </div>

            <div
              className="result-list"
              role="listbox"
              aria-label="Search results"
              tabIndex={0}
              onKeyDown={handleResultListKeyDown}
              ref={resultListRef}
            >
              {results.map((result) => {
                const visibleAttachments = result.attachments.filter((attachment) => !isThumbnailImage(attachment)).slice(0, 3);
                const rowClasses = ["result-row", selectedId === result.id ? "selected" : "", isMeetingRequest(result) ? "meeting-request" : ""]
                  .filter(Boolean)
                  .join(" ");
                return (
                  <button
                    key={result.id}
                    data-result-id={result.id}
                    className={rowClasses}
                    aria-selected={selectedId === result.id}
                    onClick={() => setSelectedId(result.id)}
                    role="option"
                    type="button"
                  >
                    <div className="result-main">
                      <div className="result-title">
                        {result.is_favorite && <Star size={14} fill="currentColor" />}
                        <span>{result.subject || "(No subject)"}</span>
                      </div>
                      <div className="result-meta">
                        <span>{displayPerson(result.sender_name, result.sender_email)}</span>
                        <span>{formatDate(result.sent_at || result.received_at)}</span>
                      </div>
                      <p dangerouslySetInnerHTML={{ __html: result.snippet || "No snippet available." }} />
                      <div className="chips">
                        {result.match_reasons.map((reason) => (
                          <span key={reason}>{reason}</span>
                        ))}
                        {visibleAttachments.map((attachment) => (
                          <span key={attachment.id}>
                            <Paperclip size={12} />
                            {attachment.filename}
                          </span>
                        ))}
                      </div>
                    </div>
                    <div className="score">
                      <strong>{result.score.toFixed(2)}</strong>
                      <span>K {result.keyword_score.toFixed(2)}</span>
                      <span>S {result.semantic_score.toFixed(2)}</span>
                    </div>
                  </button>
                );
              })}
              {!loading && results.length === 0 && (
                <div className="empty">
                  <Inbox size={24} />
                  No messages matched the current search.
                </div>
              )}
            </div>

            {!loading && totalPages > 1 && (
              <div className="pager">
                <button disabled={offset === 0 || loading} onClick={() => void runSearch(Math.max(0, offset - PAGE_SIZE))}>
                  Previous
                </button>
                <button disabled={offset + PAGE_SIZE >= total || loading} onClick={() => void runSearch(offset + PAGE_SIZE)}>
                  Next
                </button>
              </div>
            )}
          </section>

          <section className="detail-pane">
            {detailLoading && (
              <div className="loading-detail">
                <Loader2 size={22} className="spin" />
              </div>
            )}
            {!detailLoading && detail && (
              <>
                <div className="detail-header">
                  <div>
                    <h1>{detail.subject || "(No subject)"}</h1>
                    <p>
                      {displayPerson(detail.sender_name, detail.sender_email)} · {formatDate(detail.sent_at || detail.received_at)}
                    </p>
                  </div>
                  <button className={detail.is_favorite ? "icon active" : "icon"} onClick={() => void toggleFavorite()} title="Favorite">
                    <Heart size={18} fill={detail.is_favorite ? "currentColor" : "none"} />
                  </button>
                </div>

                <div className="meta-grid">
                  <span>From</span>
                  <strong>{displayPerson(detail.sender_name, detail.sender_email)}</strong>
                  <span>To/Cc/Bcc</span>
                  <strong>{displayRecipients(detail.recipients)}</strong>
                  <span>Sources</span>
                  <strong>{detail.occurrences.map((item) => item.folder_path || item.pst_path).join(" · ") || "Unknown"}</strong>
                </div>

                <div className="attachment-strip">
                  {visibleDetailAttachments.map((attachment) => (
                    <div key={attachment.id} className={isThumbnailImage(attachment) ? "attachment-item image-card" : "attachment-item"}>
                      {isThumbnailImage(attachment) ? (
                        <a
                          className="attachment-thumb image"
                          href={attachmentPreviewUrl(attachment.id)}
                          target="_blank"
                          rel="noreferrer"
                          aria-label={`Open ${attachment.filename} in a new tab`}
                          title={attachment.filename}
                        >
                          <img src={attachmentPreviewUrl(attachment.id)} alt="" loading="lazy" />
                        </a>
                      ) : (
                        <span className="attachment-thumb icon">
                          <Paperclip size={15} />
                        </span>
                      )}
                      {!isThumbnailImage(attachment) && (
                        <>
                          <div>
                            <strong>{attachment.filename}</strong>
                            <span>
                              {attachment.mime_type || "file"} · {formatBytes(attachment.size_bytes)} · {attachment.extraction_status}
                            </span>
                          </div>
                          <a href={attachmentPreviewUrl(attachment.id)} target="_blank" rel="noreferrer" title="Preview">
                            <FileText size={16} />
                          </a>
                          <a href={attachmentDownloadUrl(attachment.id)} title="Download">
                            <Download size={16} />
                          </a>
                        </>
                      )}
                    </div>
                  ))}
                  {visibleDetailAttachments.length === 0 && <span className="muted">No attachments</span>}
                </div>

                <div className="note-editor">
                  <label>Notes</label>
                  <textarea value={noteDraft} onChange={(event) => setNoteDraft(event.target.value)} />
                  <button onClick={() => void persistNote()} disabled={!noteHasChanges || noteSaving}>
                    {noteSaving ? <Loader2 size={16} className="spin" /> : <Save size={16} />}
                    {noteSaving ? "Saving" : "Save note"}
                  </button>
                </div>

                <article className="email-body">
                  {detail.body_html ? (
                    <div dangerouslySetInnerHTML={{ __html: detail.body_html }} />
                  ) : (
                    <pre>{detail.body_text || selectedResult?.snippet || "No body text extracted."}</pre>
                  )}
                </article>
              </>
            )}
            {!detailLoading && !detail && (
              <div className="empty detail-empty">
                <Mail size={28} />
                Select a message to view it.
              </div>
            )}
          </section>
        </main>
      ) : (
        <ImportPanel />
      )}
    </div>
  );
}

function ImportPanel() {
  const [files, setFiles] = useState<ImportFile[]>([]);
  const [jobs, setJobs] = useState<ImportJob[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const refresh = useCallback(async () => {
    setError(null);
    try {
      const [scan, importJobs] = await Promise.all([scanImports(), listImports()]);
      setFiles(scan.files);
      setJobs(importJobs);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to refresh imports.");
    }
  }, []);

  useEffect(() => {
    void refresh();
    const timer = window.setInterval(() => void refresh(), 4000);
    return () => window.clearInterval(timer);
  }, [refresh]);

  async function startImport(file: ImportFile) {
    setLoading(true);
    setError(null);
    try {
      await createImport(file.relative_path);
      await refresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start import.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <main className="import-layout">
      <section className="import-column">
        <div className="section-title">
          <div>
            <h1>Watched PST Folder</h1>
            <p>Copy `.pst` files into `data/imports`, then start an import.</p>
          </div>
          <button onClick={() => void refresh()} disabled={loading}>
            <RefreshCw size={16} />
            Refresh
          </button>
        </div>
        {error && <div className="notice error">{error}</div>}
        <div className="file-list">
          {files.map((file) => (
            <div key={file.source_path} className="file-row">
              <FileText size={20} />
              <div>
                <strong>{file.filename}</strong>
                <span>
                  {formatBytes(file.file_size)} · modified {formatDate(new Date(file.modified_at * 1000).toISOString())}
                </span>
              </div>
              <button onClick={() => void startImport(file)} disabled={loading}>
                <FolderSync size={16} />
                Import
              </button>
            </div>
          ))}
          {files.length === 0 && (
            <div className="empty">
              <Filter size={24} />
              No PST files found in the watched folder.
            </div>
          )}
        </div>
      </section>

      <section className="import-column">
        <div className="section-title">
          <div>
            <h1>Import Jobs</h1>
            <p>Progress includes duplicate collapse, attachments, and semantic chunks.</p>
          </div>
        </div>
        <div className="job-list">
          {jobs.map((job) => (
            <div key={job.id} className={`job-row ${job.status}`}>
              <div className="job-status">
                {statusIcon(job.status)}
                <strong>{job.status}</strong>
              </div>
              <div className="job-main">
                <strong>{job.source_filename}</strong>
                <span>{formatBytes(job.file_size)}</span>
                {job.last_error && <span className="job-error">{job.last_error}</span>}
              </div>
              <div className="job-stats">
                <span>{job.processed_count.toLocaleString()} processed</span>
                <span>{job.inserted_count.toLocaleString()} new</span>
                <span>{job.duplicate_count.toLocaleString()} duplicates</span>
                <span>{job.attachment_count.toLocaleString()} attachments</span>
                <span>{job.semantic_indexed_count.toLocaleString()} vectors</span>
                <span>{job.error_count.toLocaleString()} errors</span>
              </div>
            </div>
          ))}
          {jobs.length === 0 && (
            <div className="empty">
              <Archive size={24} />
              No imports have been created.
            </div>
          )}
        </div>
      </section>
    </main>
  );
}

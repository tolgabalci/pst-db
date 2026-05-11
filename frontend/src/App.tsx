import {
  Archive,
  Calendar,
  CheckCircle2,
  Database,
  Download,
  FileText,
  Filter,
  Folder,
  FolderSync,
  Heart,
  Inbox,
  Loader2,
  Mail,
  Paperclip,
  RefreshCw,
  Save,
  Search,
  Settings as SettingsIcon,
  SlidersHorizontal,
  Star,
  UserRound,
  XCircle
} from "lucide-react";
import { FormEvent, KeyboardEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  API_BASE,
  applyClientCacheSettings,
  attachmentDownloadUrl,
  attachmentPreviewUrl,
  createImport,
  DEFAULT_APP_SETTINGS,
  getAppSettings,
  getEmail,
  getEmailAttachments,
  listSearchFolders,
  listImports,
  saveNote,
  scanImports,
  searchEmails,
  setFavorite,
  updateAppSettings
} from "./api";
import type { AppSettings, AttachmentDetail, EmailDetail, ImportFile, ImportJob, MailboxFolder, SearchMode, SearchResult } from "./types";

const PAGE_SIZE = 50;
const THUMBNAIL_IMAGE_TYPES = new Set(["image/png", "image/jpeg", "image/gif", "image/webp", "image/bmp"]);
const DEFAULT_FOLDER_NAMES = new Set(["inbox", "not directed", "sent", "sent items", "sent mail"]);

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

function folderName(folderPath: string): string {
  const parts = folderPath.split(/[\\/]/).filter(Boolean);
  return parts[parts.length - 1] || folderPath;
}

function isDefaultFolder(folderPath: string): boolean {
  return DEFAULT_FOLDER_NAMES.has(folderName(folderPath).trim().toLocaleLowerCase());
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

function importKey(value: string | null | undefined): string {
  return (value || "").replace(/\\/g, "/").trim().toLocaleLowerCase();
}

function isAlreadyImportedFile(file: ImportFile, completedJobKeys: Set<string>): boolean {
  return [file.source_path, file.relative_path, file.filename].map(importKey).some((key) => completedJobKeys.has(key));
}

function matchedImportStatus(file: ImportFile, jobStatusByKey: Map<string, string>): string | null {
  const keys = [file.source_path, file.relative_path, file.filename].map(importKey);
  for (const key of keys) {
    const status = jobStatusByKey.get(key);
    if (status && status !== "failed") return status;
  }
  return null;
}

function statusLabel(status: string): string {
  return status ? status[0].toUpperCase() + status.slice(1) : "";
}

export function App() {
  const [tab, setTab] = useState<"search" | "imports" | "settings">("search");
  const [appSettings, setAppSettings] = useState<AppSettings>(DEFAULT_APP_SETTINGS);
  const [settingsLoaded, setSettingsLoaded] = useState(false);
  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<SearchMode>("all");
  const [author, setAuthor] = useState("");
  const [recipient, setRecipient] = useState("");
  const [folderOptions, setFolderOptions] = useState<MailboxFolder[]>([]);
  const [selectedFolders, setSelectedFolders] = useState<string[]>([]);
  const [foldersLoaded, setFoldersLoaded] = useState(false);
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

  useEffect(() => {
    let canceled = false;
    getAppSettings()
      .then((settings) => {
        if (canceled) return;
        setAppSettings(settings);
        applyClientCacheSettings(settings);
      })
      .catch((err) => {
        if (!canceled) setError(err instanceof Error ? err.message : "Failed to load settings.");
      })
      .finally(() => {
        if (!canceled) setSettingsLoaded(true);
      });
    return () => {
      canceled = true;
    };
  }, []);

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
          folders: folderOptions.length > 0 ? selectedFolders : undefined,
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
    [
      attachmentFilename,
      author,
      dateFrom,
      dateTo,
      favoriteOnly,
      folderOptions.length,
      hasAttachments,
      mode,
      query,
      recipient,
      selectedFolders,
      subject
    ]
  );

  useEffect(() => {
    if (!settingsLoaded) return;
    let canceled = false;
    listSearchFolders()
      .then((folders) => {
        if (canceled) return;
        setFolderOptions(folders);
        const defaultFolders = folders.filter((folder) => isDefaultFolder(folder.folder_path)).map((folder) => folder.folder_path);
        setSelectedFolders(defaultFolders.length ? defaultFolders : folders.map((folder) => folder.folder_path));
      })
      .catch((err) => {
        if (!canceled) setError(err instanceof Error ? err.message : "Failed to load mailbox folders.");
      })
      .finally(() => {
        if (!canceled) setFoldersLoaded(true);
      });
    return () => {
      canceled = true;
    };
  }, [settingsLoaded]);

  useEffect(() => {
    if (foldersLoaded) void runSearch(0);
  }, [foldersLoaded]);

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
  const defaultSelectedFolders = useMemo(
    () => folderOptions.filter((folder) => isDefaultFolder(folder.folder_path)).map((folder) => folder.folder_path),
    [folderOptions]
  );
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

  function toggleFolder(folderPath: string, checked: boolean) {
    setSelectedFolders((current) =>
      checked ? [...new Set([...current, folderPath])] : current.filter((item) => item !== folderPath)
    );
  }

  function selectDefaultFolders() {
    setSelectedFolders(defaultSelectedFolders.length ? defaultSelectedFolders : folderOptions.map((folder) => folder.folder_path));
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
          <button className={tab === "settings" ? "active" : ""} onClick={() => setTab("settings")}>
            <SettingsIcon size={16} />
            Settings
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

              <details className="folder-filter">
                <summary>
                  <Folder size={14} />
                  <span>Folders</span>
                  <strong>
                    {folderOptions.length === 0
                      ? "All"
                      : selectedFolders.length === folderOptions.length
                        ? "All"
                        : `${selectedFolders.length}/${folderOptions.length}`}
                  </strong>
                </summary>
                <div className="folder-menu">
                  <div className="folder-actions">
                    <button type="button" onClick={selectDefaultFolders}>
                      Default
                    </button>
                    <button type="button" onClick={() => setSelectedFolders(folderOptions.map((folder) => folder.folder_path))}>
                      All
                    </button>
                  </div>
                  <div className="folder-options">
                    {folderOptions.map((folder) => (
                      <label key={folder.folder_path} title={folder.folder_path}>
                        <input
                          type="checkbox"
                          checked={selectedFolders.includes(folder.folder_path)}
                          onChange={(event) => toggleFolder(folder.folder_path, event.target.checked)}
                        />
                        <span>{folderName(folder.folder_path)}</span>
                        <small>{folder.email_count.toLocaleString()}</small>
                      </label>
                    ))}
                    {folderOptions.length === 0 && <span className="muted">No folders</span>}
                  </div>
                </div>
              </details>

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
      ) : tab === "imports" ? (
        <ImportPanel />
      ) : (
        <SettingsPanel
          settings={appSettings}
          onSave={(settings) => {
            setAppSettings(settings);
            applyClientCacheSettings(settings);
          }}
        />
      )}
    </div>
  );
}

function ImportPanel() {
  const [files, setFiles] = useState<ImportFile[]>([]);
  const [jobs, setJobs] = useState<ImportJob[]>([]);
  const [showImportedFiles, setShowImportedFiles] = useState(false);
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

  const completedJobKeys = useMemo(
    () =>
      new Set(
        jobs
          .filter((job) => job.status === "completed")
          .flatMap((job) => [job.source_path, job.source_filename])
          .map(importKey)
          .filter(Boolean)
      ),
    [jobs]
  );
  const jobStatusByKey = useMemo(() => {
    const statusPriority = new Map([
      ["running", 4],
      ["queued", 3],
      ["completed", 2],
      ["failed", 1]
    ]);
    const statuses = new Map<string, string>();
    for (const job of jobs) {
      for (const key of [job.source_path, job.source_filename].map(importKey).filter(Boolean)) {
        const current = statuses.get(key);
        if (!current || (statusPriority.get(job.status) || 0) > (statusPriority.get(current) || 0)) {
          statuses.set(key, job.status);
        }
      }
    }
    return statuses;
  }, [jobs]);
  const visibleFiles = useMemo(
    () => (showImportedFiles ? files : files.filter((file) => !isAlreadyImportedFile(file, completedJobKeys))),
    [completedJobKeys, files, showImportedFiles]
  );
  const hiddenImportedCount = files.length - visibleFiles.length;

  return (
    <main className="import-layout">
      <section className="import-column">
        <div className="section-title">
          <div>
            <h1>Watched PST Folder</h1>
            <p>Copy `.pst` files into `data/imports`, then start an import.</p>
          </div>
          <div className="section-actions">
            <label className="check">
              <input
                type="checkbox"
                checked={showImportedFiles}
                onChange={(event) => setShowImportedFiles(event.target.checked)}
              />
              Show imported
            </label>
            <button onClick={() => void refresh()} disabled={loading}>
              <RefreshCw size={16} />
              Refresh
            </button>
          </div>
        </div>
        {error && <div className="notice error">{error}</div>}
        {!showImportedFiles && hiddenImportedCount > 0 && (
          <div className="notice info">{hiddenImportedCount.toLocaleString()} imported PST file hidden.</div>
        )}
        <div className="file-list">
          {visibleFiles.map((file) => {
            const importStatus = matchedImportStatus(file, jobStatusByKey);
            return (
              <div key={file.source_path} className="file-row">
                <FileText size={20} />
                <div>
                  <strong>{file.filename}</strong>
                  <span>
                    {formatBytes(file.file_size)} · modified {formatDate(new Date(file.modified_at * 1000).toISOString())}
                  </span>
                </div>
                {importStatus ? (
                  <span className={`file-status ${importStatus}`}>
                    {statusIcon(importStatus)}
                    {statusLabel(importStatus)}
                  </span>
                ) : (
                  <button onClick={() => void startImport(file)} disabled={loading}>
                    <FolderSync size={16} />
                    Import
                  </button>
                )}
              </div>
            );
          })}
          {visibleFiles.length === 0 && (
            <div className="empty">
              <Filter size={24} />
              {hiddenImportedCount > 0 ? "No new PST files found in the watched folder." : "No PST files found in the watched folder."}
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

type SettingsField = {
  key: keyof AppSettings;
  label: string;
  help: string;
  min: number;
  max: number;
  unit: string;
};

const SETTINGS_FIELDS: SettingsField[] = [
  {
    key: "search_result_cache_entries",
    label: "Search result cache size",
    help: "Maximum backend search pages kept in memory.",
    min: 0,
    max: 10000,
    unit: "entries"
  },
  {
    key: "search_result_cache_ttl_seconds",
    label: "Search result cache lifetime",
    help: "How long cached backend search pages can be reused.",
    min: 0,
    max: 86400,
    unit: "seconds"
  },
  {
    key: "query_embedding_cache_entries",
    label: "Query embedding cache size",
    help: "Maximum semantic query vectors kept in backend memory.",
    min: 0,
    max: 50000,
    unit: "entries"
  },
  {
    key: "query_embedding_cache_ttl_seconds",
    label: "Query embedding cache lifetime",
    help: "How long repeated semantic query vectors are reused.",
    min: 0,
    max: 604800,
    unit: "seconds"
  },
  {
    key: "folder_list_cache_entries",
    label: "Folder list cache size",
    help: "Maximum backend folder-list versions kept in memory.",
    min: 0,
    max: 1000,
    unit: "entries"
  },
  {
    key: "folder_list_cache_ttl_seconds",
    label: "Folder list cache lifetime",
    help: "How long mailbox folder lists can be reused.",
    min: 0,
    max: 3600,
    unit: "seconds"
  },
  {
    key: "import_status_cache_entries",
    label: "Import status cache size",
    help: "Maximum import status responses kept in memory.",
    min: 0,
    max: 1000,
    unit: "entries"
  },
  {
    key: "import_status_cache_ttl_seconds",
    label: "Import status cache lifetime",
    help: "How long import scan and job status responses can be reused.",
    min: 0,
    max: 300,
    unit: "seconds"
  },
  {
    key: "email_detail_cache_entries",
    label: "Email detail browser cache size",
    help: "Maximum opened messages kept in the browser session.",
    min: 0,
    max: 10000,
    unit: "entries"
  },
  {
    key: "attachment_metadata_cache_entries",
    label: "Attachment metadata browser cache size",
    help: "Maximum attachment lists kept in the browser session.",
    min: 0,
    max: 10000,
    unit: "entries"
  },
  {
    key: "attachment_preview_cache_max_age_seconds",
    label: "Attachment preview browser cache lifetime",
    help: "Cache-Control max age sent for previews and downloads.",
    min: 0,
    max: 2592000,
    unit: "seconds"
  }
];

function SettingsPanel({ settings, onSave }: { settings: AppSettings; onSave: (settings: AppSettings) => void }) {
  const [draft, setDraft] = useState<AppSettings>(settings);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setDraft(settings);
  }, [settings]);

  const hasChanges = JSON.stringify(draft) !== JSON.stringify(settings);

  function setValue(key: keyof AppSettings, value: string) {
    const parsed = Number.parseInt(value, 10);
    setDraft((current) => ({ ...current, [key]: Number.isFinite(parsed) ? parsed : 0 }));
  }

  async function saveSettings(nextSettings = draft) {
    setSaving(true);
    setError(null);
    setMessage(null);
    try {
      const saved = await updateAppSettings(nextSettings);
      setDraft(saved);
      onSave(saved);
      setMessage("Settings saved.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save settings.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <main className="settings-layout">
      <section className="settings-header">
        <div>
          <h1>Settings</h1>
          <p>Runtime cache limits for this local site.</p>
        </div>
        <SlidersHorizontal size={22} />
      </section>

      {error && <div className="notice error">{error}</div>}
      {message && <div className="notice success">{message}</div>}

      <section className="settings-panel">
        <div className="settings-grid">
          {SETTINGS_FIELDS.map((field) => (
            <label key={field.key} className="setting-row">
              <span>
                <strong>{field.label}</strong>
                <small>{field.help}</small>
              </span>
              <span className="setting-control">
                <input
                  type="number"
                  min={field.min}
                  max={field.max}
                  value={draft[field.key]}
                  onChange={(event) => setValue(field.key, event.target.value)}
                />
                <em>{field.unit}</em>
              </span>
            </label>
          ))}
        </div>
        <div className="settings-actions">
          <button type="button" onClick={() => void saveSettings(DEFAULT_APP_SETTINGS)} disabled={saving}>
            Restore defaults
          </button>
          <button type="button" className="primary" onClick={() => void saveSettings()} disabled={!hasChanges || saving}>
            {saving ? <Loader2 size={16} className="spin" /> : <Save size={16} />}
            {saving ? "Saving" : "Save settings"}
          </button>
        </div>
      </section>
    </main>
  );
}

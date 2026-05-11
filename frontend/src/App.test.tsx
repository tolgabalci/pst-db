import "@testing-library/jest-dom/vitest";

import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, test, vi } from "vitest";

import type { AppSettings, ImportFile, ImportJob } from "./types";

const mockState = vi.hoisted(() => ({
  files: [] as ImportFile[],
  jobs: [] as ImportJob[],
  settings: {
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
  } as AppSettings
}));

vi.mock("./api", () => ({
  API_BASE: "http://localhost:8000",
  DEFAULT_APP_SETTINGS: mockState.settings,
  applyClientCacheSettings: vi.fn(),
  attachmentDownloadUrl: (id: string) => `http://localhost:8000/api/attachments/${id}/download`,
  attachmentPreviewUrl: (id: string) => `http://localhost:8000/api/attachments/${id}/preview`,
  createImport: vi.fn(() => Promise.resolve(makeJob("New.PST", "queued"))),
  getAppSettings: vi.fn(() => Promise.resolve(mockState.settings)),
  getEmail: vi.fn(),
  getEmailAttachments: vi.fn(),
  listImports: vi.fn(() => Promise.resolve(mockState.jobs)),
  listSearchFolders: vi.fn(() => Promise.resolve([])),
  saveNote: vi.fn(),
  scanImports: vi.fn(() => Promise.resolve({ files: mockState.files })),
  searchEmails: vi.fn(() => Promise.resolve({ results: [], total: 0, semantic_error: null })),
  setFavorite: vi.fn(),
  updateAppSettings: vi.fn((settings: AppSettings) => Promise.resolve(settings))
}));

import { App } from "./App";
import { createImport } from "./api";

describe("Imports tab", () => {
  beforeEach(() => {
    mockState.files = [];
    mockState.jobs = [];
    vi.clearAllMocks();
  });

  test("hides already imported PST files by default", async () => {
    mockState.files = [makeFile("Archive.PST"), makeFile("New.PST")];
    mockState.jobs = [makeJob("archive.pst", "completed", "c:/data/imports/archive.pst")];

    await renderImportsTab();

    expect(importFileList().queryByText("Archive.PST")).not.toBeInTheDocument();
    expect(importFileList().getByText("New.PST")).toBeInTheDocument();
    expect(screen.getByText("1 imported PST file hidden.")).toBeInTheDocument();
    expect(screen.getByLabelText("Show imported")).not.toBeChecked();
  });

  test("shows imported PST files when the toggle is selected", async () => {
    mockState.files = [makeFile("Archive.PST"), makeFile("New.PST")];
    mockState.jobs = [makeJob("Archive.PST", "completed")];

    await renderImportsTab();
    fireEvent.click(screen.getByLabelText("Show imported"));

    expect(importFileList().getByText("Archive.PST")).toBeInTheDocument();
    expect(importFileList().getByText("New.PST")).toBeInTheDocument();
    expect(screen.queryByText("1 imported PST file hidden.")).not.toBeInTheDocument();
  });

  test("does not hide files from failed imports", async () => {
    mockState.files = [makeFile("Retry.PST")];
    mockState.jobs = [makeJob("Retry.PST", "failed")];

    await renderImportsTab();

    expect(importFileList().getByText("Retry.PST")).toBeInTheDocument();
    expect(screen.queryByText("imported PST file hidden.")).not.toBeInTheDocument();
  });

  test("shows queued PST files as queued instead of importable", async () => {
    mockState.files = [makeFile("Queued.PST")];
    mockState.jobs = [makeJob("queued.pst", "queued", "c:/data/imports/queued.pst")];

    await renderImportsTab();

    const fileList = importFileList();
    expect(fileList.getByText("Queued.PST")).toBeInTheDocument();
    expect(fileList.getByText("Queued")).toBeInTheDocument();
    expect(fileList.queryByRole("button", { name: "Import" })).not.toBeInTheDocument();
  });

  test("shows running PST files as running instead of importable", async () => {
    mockState.files = [makeFile("Running.PST")];
    mockState.jobs = [makeJob("running.pst", "running", "c:/data/imports/running.pst")];

    await renderImportsTab();

    const fileList = importFileList();
    expect(fileList.getByText("Running.PST")).toBeInTheDocument();
    expect(fileList.getByText("running")).toBeInTheDocument();
    expect(fileList.queryByRole("button", { name: "Import" })).not.toBeInTheDocument();
  });

  test("hides the import button immediately after starting an import", async () => {
    mockState.files = [makeFile("Started.PST")];
    let finishImport: ((job: ImportJob) => void) | undefined;
    vi.mocked(createImport).mockImplementationOnce(
      () =>
        new Promise<ImportJob>((resolve) => {
          finishImport = resolve;
        })
    );

    await renderImportsTab();
    const fileList = importFileList();
    fireEvent.click(fileList.getByRole("button", { name: "Import" }));

    await waitFor(() => expect(fileList.getByText("Queued")).toBeInTheDocument());
    expect(fileList.queryByRole("button", { name: "Import" })).not.toBeInTheDocument();

    mockState.jobs = [makeJob("Started.PST", "queued")];
    finishImport?.(makeJob("Started.PST", "queued"));
  });

  test("restores the import button when starting an import fails", async () => {
    mockState.files = [makeFile("FailedStart.PST")];
    vi.mocked(createImport).mockRejectedValueOnce(new Error("Failed to queue import."));

    await renderImportsTab();
    const fileList = importFileList();
    fireEvent.click(fileList.getByRole("button", { name: "Import" }));

    await screen.findByText("Failed to queue import.");
    expect(fileList.getByRole("button", { name: "Import" })).toBeInTheDocument();
    expect(fileList.queryByText("Queued")).not.toBeInTheDocument();
  });

  test("shows estimated remaining time for running imports when completed import history exists", async () => {
    const now = Date.now();
    mockState.jobs = [
      makeJob("Done.PST", "completed", "C:\\Data\\Imports\\Done.PST", {
        file_size: 1000,
        started_at: "2026-05-09T00:00:00Z",
        finished_at: "2026-05-09T00:00:10Z"
      }),
      makeJob("Running.PST", "running", "C:\\Data\\Imports\\Running.PST", {
        file_size: 2000,
        started_at: new Date(now - 5000).toISOString()
      })
    ];

    await renderImportsTab();

    expect(screen.getByText("Estimated remaining: 15 sec")).toBeInTheDocument();
  });

  test("shows estimating remaining time when no completed import history exists", async () => {
    mockState.jobs = [
      makeJob("Running.PST", "running", "C:\\Data\\Imports\\Running.PST", {
        file_size: 2000,
        started_at: "2026-05-10T00:00:00Z"
      })
    ];

    await renderImportsTab();

    expect(screen.getByText("Estimated remaining: estimating")).toBeInTheDocument();
  });
});

async function renderImportsTab() {
  render(<App />);
  fireEvent.click(await screen.findByRole("button", { name: "Imports" }));
  await screen.findByText("Watched PST Folder");
  return within(screen.getByRole("main"));
}

function importFileList() {
  const element = document.querySelector(".file-list");
  if (!element) throw new Error("Expected import file list to exist.");
  return within(element as HTMLElement);
}

function makeFile(filename: string): ImportFile {
  return {
    filename,
    source_path: `C:\\Data\\Imports\\${filename}`,
    relative_path: filename,
    file_size: 1024,
    modified_at: 1_715_000_000
  };
}

function makeJob(
  filename: string,
  status: string,
  sourcePath = `C:\\Data\\Imports\\${filename}`,
  overrides: Partial<ImportJob> = {}
): ImportJob {
  return {
    id: `job-${filename}-${status}`,
    source_filename: filename,
    source_path: sourcePath,
    file_size: 1024,
    sha256: null,
    status,
    processed_count: 0,
    inserted_count: 0,
    duplicate_count: 0,
    attachment_count: 0,
    semantic_indexed_count: 0,
    error_count: 0,
    last_error: null,
    created_at: "2026-05-10T00:00:00Z",
    started_at: null,
    finished_at: null,
    ...overrides
  };
}

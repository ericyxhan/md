import type {
  Artifact,
  ArtifactList,
  Capabilities,
  EventWithJobOut,
  FileInspect,
  FileOut,
  Job,
  JobCreate,
  JobEvent,
  JobList,
  JobPlan,
  JobSpec,
  LogEntry,
  LogList,
  LogTail,
  MembraneEmbedOut,
  MembraneEmbedRequest,
  PDBInspection,
  PrepJobStatus,
  RetryMode,
  SessionInfo,
  SeriesOut,
  SystemPrepOut,
  SystemPrepRequest,
  ViewList,
  WorkflowCreate,
  WorkflowDetailOut,
  WorkflowJobSummary,
  WorkflowOut,
  WorkflowVariantsRequest,
} from "./types";

const API_BASE = "/api/v1";

export class ApiError extends Error {
  status: number;
  code: string;
  details?: Record<string, unknown>;
  requestId?: string | null;

  constructor(
    status: number,
    code: string,
    message: string,
    details?: Record<string, unknown>,
    requestId?: string | null,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
    this.requestId = requestId;
  }
}

export function readCookie(name: string): string | null {
  const prefix = `${name}=`;
  for (const part of document.cookie.split(";")) {
    const value = part.trim();
    if (value.startsWith(prefix)) {
      return decodeURIComponent(value.slice(prefix.length));
    }
  }
  return null;
}

function mutatingHeaders(method: string): Record<string, string> {
  if (["GET", "HEAD", "OPTIONS"].includes(method.toUpperCase())) return {};
  const token = readCookie("md_csrf");
  return token ? { "X-CSRF-Token": token } : {};
}

interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  rawBody?: BodyInit;
  expect?: "json" | "text" | "none";
}

async function request<T>(
  path: string,
  { body, rawBody, expect = "json", ...init }: RequestOptions = {},
): Promise<T> {
  const method = (init.method ?? "GET").toUpperCase();
  const headers = new Headers(init.headers);
  headers.set("Accept", expect === "text" ? "text/plain" : "application/json");
  for (const [key, value] of Object.entries(mutatingHeaders(method))) {
    headers.set(key, value);
  }

  let payload = rawBody;
  if (body !== undefined) {
    headers.set("Content-Type", "application/json");
    payload = JSON.stringify(body);
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      method,
      headers,
      body: payload,
      credentials: "same-origin",
    });
  } catch (error) {
    throw new ApiError(
      0,
      "network_error",
      error instanceof Error ? error.message : "Could not reach the server",
    );
  }

  if (!response.ok) {
    if (response.status === 401 && path !== "/session") {
      window.dispatchEvent(new CustomEvent("md:unauthorized"));
    }
    let code = `http_${response.status}`;
    let message = response.statusText || "Request failed";
    let details: Record<string, unknown> | undefined;
    try {
      const parsed = await response.json();
      code = parsed?.error?.code ?? code;
      message = parsed?.error?.message ?? message;
      details = parsed?.error?.details;
    } catch {
      // Leave the status-derived message in place.
    }
    throw new ApiError(
      response.status,
      code,
      message,
      details,
      response.headers.get("X-Request-ID"),
    );
  }

  if (response.status === 204 || expect === "none") {
    return undefined as T;
  }
  if (expect === "text") {
    return (await response.text()) as T;
  }
  return (await response.json()) as T;
}

// ---------------------------------------------------------------------------
// Session
// ---------------------------------------------------------------------------

export function getSession(): Promise<SessionInfo> {
  return request<SessionInfo>("/session");
}

export function login(password: string): Promise<SessionInfo> {
  return request<SessionInfo>("/session", {
    method: "POST",
    body: { password },
  });
}

export function logout(): Promise<void> {
  return request<void>("/session/logout", {
    method: "POST",
    expect: "none",
  });
}

// ---------------------------------------------------------------------------
// Capabilities and files
// ---------------------------------------------------------------------------

export function getCapabilities(): Promise<Capabilities> {
  return request<Capabilities>("/capabilities");
}

export function uploadFile(
  file: File,
  onProgress?: (percent: number) => void,
): Promise<FileOut> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${API_BASE}/files`);
    xhr.withCredentials = true;
    const csrf = readCookie("md_csrf");
    if (csrf) xhr.setRequestHeader("X-CSRF-Token", csrf);
    xhr.setRequestHeader("Accept", "application/json");

    xhr.upload.addEventListener("progress", (event) => {
      if (event.lengthComputable) {
        onProgress?.(Math.round((event.loaded / event.total) * 100));
      }
    });

    xhr.addEventListener("load", () => {
      let parsed: unknown = null;
      try {
        parsed = JSON.parse(xhr.responseText);
      } catch {
        // Fall through to the status-based error below.
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        onProgress?.(100);
        resolve(parsed as FileOut);
        return;
      }
      const body = parsed as
        | { error?: { code?: string; message?: string; details?: never } }
        | null;
      reject(
        new ApiError(
          xhr.status,
          body?.error?.code ?? `http_${xhr.status}`,
          body?.error?.message ?? "Upload failed",
          body?.error?.details,
          xhr.getResponseHeader("X-Request-ID"),
        ),
      );
    });

    xhr.addEventListener("error", () => {
      reject(new ApiError(0, "network_error", "Upload failed"));
    });
    xhr.addEventListener("abort", () => {
      reject(new ApiError(0, "upload_aborted", "Upload canceled"));
    });

    const form = new FormData();
    form.append("file", file);
    xhr.send(form);
  });
}

// ---------------------------------------------------------------------------
// Jobs
// ---------------------------------------------------------------------------

export function listJobs(params: {
  status?: string;
  limit?: number;
  cursor?: string | null;
} = {}): Promise<JobList> {
  const query = new URLSearchParams();
  if (params.status) query.set("status", params.status);
  if (params.limit) query.set("limit", String(params.limit));
  if (params.cursor) query.set("cursor", params.cursor);
  const suffix = query.toString();
  return request<JobList>(`/jobs${suffix ? `?${suffix}` : ""}`);
}

export function getJob(id: string): Promise<Job> {
  return request<Job>(`/jobs/${encodeURIComponent(id)}`);
}

export function createJob(payload: JobCreate): Promise<Job> {
  return request<Job>("/jobs", { method: "POST", body: payload });
}

export function validateJob(payload: JobCreate): Promise<JobPlan> {
  return request<JobPlan>("/jobs/validate", {
    method: "POST",
    body: payload,
  });
}

export function cancelJob(id: string): Promise<Job> {
  return request<Job>(`/jobs/${encodeURIComponent(id)}/cancel`, {
    method: "POST",
  });
}

export function retryJob(
  id: string,
  mode: RetryMode,
  stage?: string,
): Promise<Job> {
  return request<Job>(`/jobs/${encodeURIComponent(id)}/retry`, {
    method: "POST",
    body: { mode, ...(stage ? { stage } : {}) },
  });
}

export function getJobEvents(
  id: string,
  afterId?: number,
  limit = 200,
): Promise<JobEvent[]> {
  const query = new URLSearchParams({ limit: String(limit) });
  if (afterId !== undefined) query.set("after_id", String(afterId));
  return request<JobEvent[]>(
    `/jobs/${encodeURIComponent(id)}/events?${query.toString()}`,
  );
}

export function getJobSpec(id: string): Promise<JobSpec> {
  return request<JobSpec>(`/jobs/${encodeURIComponent(id)}/spec`);
}

export function getJobConfig(id: string): Promise<string> {
  return request<string>(`/jobs/${encodeURIComponent(id)}/config`, {
    expect: "text",
  });
}

export function getJobViews(id: string): Promise<ViewList> {
  return request<ViewList>(`/jobs/${encodeURIComponent(id)}/views`);
}

export function getJobSeries(id: string): Promise<SeriesOut> {
  return request<SeriesOut>(`/jobs/${encodeURIComponent(id)}/analysis/series`);
}

// ---------------------------------------------------------------------------
// Artifacts and logs
// ---------------------------------------------------------------------------

export function getArtifacts(
  id: string,
  filters: { kind?: string; stage?: string } = {},
): Promise<ArtifactList> {
  const query = new URLSearchParams();
  if (filters.kind) query.set("kind", filters.kind);
  if (filters.stage) query.set("stage", filters.stage);
  const suffix = query.toString();
  return request<ArtifactList>(
    `/jobs/${encodeURIComponent(id)}/artifacts${suffix ? `?${suffix}` : ""}`,
  );
}

export function artifactUrl(jobId: string, artifact: Artifact): string {
  return `${API_BASE}/jobs/${encodeURIComponent(jobId)}/artifacts/${encodeURIComponent(artifact.id)}`;
}

export function getLogs(id: string): Promise<LogList> {
  return request<LogList>(`/jobs/${encodeURIComponent(id)}/logs`);
}

export function getLogTail(
  id: string,
  relativePath: string,
  lines = 200,
): Promise<LogTail> {
  const encodedPath = relativePath
    .split("/")
    .map((part) => encodeURIComponent(part))
    .join("/");
  return request<LogTail>(
    `/jobs/${encodeURIComponent(id)}/logs/${encodedPath}/tail?lines=${lines}`,
  );
}

export function logDownloadUrl(jobId: string, entry: LogEntry): string {
  const encodedPath = entry.relative_path
    .split("/")
    .map((part) => encodeURIComponent(part))
    .join("/");
  return `${API_BASE}/jobs/${encodeURIComponent(jobId)}/logs/${encodedPath}`;
}

export function jobStreamUrl(id: string, afterId?: number): string {
  const suffix =
    afterId !== undefined ? `?after_id=${encodeURIComponent(afterId)}` : "";
  return `${API_BASE}/jobs/${encodeURIComponent(id)}/events/stream${suffix}`;
}

export function downloadArtifact(jobId: string, artifact: Artifact): void {
  const anchor = document.createElement("a");
  anchor.href = artifactUrl(jobId, artifact);
  anchor.download = artifact.name;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
}

// ---------------------------------------------------------------------------
// System preparation
// ---------------------------------------------------------------------------

export function getFile(id: string): Promise<FileOut> {
  return request<FileOut>(`/files/${encodeURIComponent(id)}`);
}

export function requestMembraneEmbed(
  payload: MembraneEmbedRequest,
): Promise<MembraneEmbedOut> {
  return request<MembraneEmbedOut>("/prep/membrane", {
    method: "POST",
    body: payload,
  });
}

export function getPrepJob(id: string): Promise<PrepJobStatus> {
  return request<PrepJobStatus>(
    `/prep/jobs/${encodeURIComponent(id)}`
  );
}

export function listPrepJobs(): Promise<PrepJobStatus[]> {
  return request<PrepJobStatus[]>("/prep/jobs");
}

export function prepFileUrl(fileId: string): string {
  return `${API_BASE}/files/${encodeURIComponent(fileId)}`;
}

/** Inline URL for rendering a raw upload in the viewer (size-guarded). */
export function filePreviewUrl(fileId: string): string {
  return `${API_BASE}/files/${encodeURIComponent(fileId)}/preview`;
}

/** Inspect a stored structure file (PDB only) for chains, ligands, components. */
export function getFileInspect(fileId: string): Promise<FileInspect> {
  return request<FileInspect>(`/files/${encodeURIComponent(fileId)}/inspect`);
}

export function cancelPrepJob(id: string): Promise<{ status: string }> {
  return request<{ status: string }>(`/prep/jobs/${encodeURIComponent(id)}/cancel`, {
    method: "POST",
  });
}

// ---------------------------------------------------------------------------
// System preparation: structure operations
// ---------------------------------------------------------------------------

export function requestSystemPrep(
  payload: SystemPrepRequest,
): Promise<SystemPrepOut> {
  return request<SystemPrepOut>("/prep/system-prep", {
    method: "POST",
    body: payload,
  });
}

/** Download a PDB from RCSB and register it as a file for previewing. */
export function fetchPdb(pdbId: string): Promise<{ file_id: string }> {
  return request<{ file_id: string }>("/prep/fetch-pdb", {
    method: "POST",
    body: { pdb_id: pdbId },
  });
}

// ---------------------------------------------------------------------------
// Workflows
// ---------------------------------------------------------------------------

export function createWorkflow(
  payload: WorkflowCreate,
): Promise<WorkflowOut> {
  return request<WorkflowOut>("/workflows", {
    method: "POST",
    body: payload,
  });
}

export function listWorkflows(): Promise<WorkflowOut[]> {
  return request<WorkflowOut[]>("/workflows");
}

export function getWorkflow(workflowId: string): Promise<WorkflowDetailOut> {
  return request<WorkflowDetailOut>(`/workflows/${encodeURIComponent(workflowId)}`);
}

export function createWorkflowVariants(
  workflowId: string,
  payload: WorkflowVariantsRequest,
): Promise<JobList> {
  return request<JobList>(
    `/workflows/${encodeURIComponent(workflowId)}/variants`,
    { method: "POST", body: payload },
  );
}

export function deleteWorkflow(workflowId: string): Promise<void> {
  return request<void>(`/workflows/${encodeURIComponent(workflowId)}`, {
    method: "DELETE",
    expect: "none",
  });
}

// ---------------------------------------------------------------------------
// Cross-job event feed (notification history)
// ---------------------------------------------------------------------------

export function getEvents(
  limit?: number,
  cursor?: string | null,
): Promise<EventWithJobOut[]> {
  const query = new URLSearchParams();
  if (limit) query.set("limit", String(limit));
  if (cursor) query.set("cursor", cursor);
  const suffix = query.toString();
  return request<EventWithJobOut[]>(`/jobs/events${suffix ? `?${suffix}` : ""}`);
}

import type {
  SessionResponse,
  DocumentUploadResponse,
  DocumentListResponse,
  QueryRequest,
  QueryResponse,
  QueryHistoryResponse,
  VoicesResponse,
  HealthResponse,
  TranscriptionResponse,
} from "@/types/api";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

class ApiError extends Error {
  constructor(
    public status: number,
    message: string
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "Unknown error" }));
    throw new ApiError(response.status, error.detail || "Request failed");
  }
  return response.json();
}

// Session endpoints
export async function createSession(): Promise<SessionResponse> {
  const response = await fetch(`${API_BASE_URL}/api/session`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({}),
  });
  return handleResponse<SessionResponse>(response);
}

export async function getSession(sessionId: string): Promise<SessionResponse> {
  const response = await fetch(`${API_BASE_URL}/api/session/${sessionId}`);
  return handleResponse<SessionResponse>(response);
}

export async function deleteSession(sessionId: string): Promise<void> {
  const response = await fetch(`${API_BASE_URL}/api/session/${sessionId}`, {
    method: "DELETE",
  });
  if (!response.ok) {
    throw new ApiError(response.status, "Failed to delete session");
  }
}

// Document endpoints
export async function uploadDocument(
  sessionId: string,
  file: File
): Promise<DocumentUploadResponse> {
  const formData = new FormData();
  formData.append("file", file);

  const response = await fetch(
    `${API_BASE_URL}/api/session/${sessionId}/documents`,
    {
      method: "POST",
      body: formData,
    }
  );
  return handleResponse<DocumentUploadResponse>(response);
}

export async function listDocuments(
  sessionId: string
): Promise<DocumentListResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/session/${sessionId}/documents`
  );
  return handleResponse<DocumentListResponse>(response);
}

export async function deleteDocument(
  sessionId: string,
  documentId: string
): Promise<void> {
  const response = await fetch(
    `${API_BASE_URL}/api/session/${sessionId}/documents/${documentId}`,
    { method: "DELETE" }
  );
  if (!response.ok) {
    throw new ApiError(response.status, "Failed to delete document");
  }
}

// Query endpoints
export async function submitQuery(
  sessionId: string,
  request: QueryRequest
): Promise<QueryResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/session/${sessionId}/query`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
    }
  );
  return handleResponse<QueryResponse>(response);
}

export async function getQueryHistory(
  sessionId: string
): Promise<QueryHistoryResponse> {
  const response = await fetch(
    `${API_BASE_URL}/api/session/${sessionId}/queries`
  );
  return handleResponse<QueryHistoryResponse>(response);
}

export function getAudioStreamUrl(sessionId: string, queryId: string): string {
  return `${API_BASE_URL}/api/session/${sessionId}/query/${queryId}/audio/stream`;
}

// Sprint 3.1 — Speech-to-Text. Posts a recorded audio blob to Whisper and
// returns the recognized text. Caller is expected to populate the query
// textarea with the result so the user can edit before submitting.
export async function transcribeAudio(
  sessionId: string,
  audioBlob: Blob,
  options: { language?: string; filename?: string } = {}
): Promise<TranscriptionResponse> {
  const filename = options.filename ?? inferFilenameFromBlob(audioBlob);

  const formData = new FormData();
  formData.append("audio", audioBlob, filename);

  const url = new URL(
    `${API_BASE_URL}/api/session/${sessionId}/transcribe`
  );
  if (options.language) {
    url.searchParams.set("language", options.language);
  }

  const response = await fetch(url.toString(), {
    method: "POST",
    body: formData,
  });
  return handleResponse<TranscriptionResponse>(response);
}

// Pick a filename Whisper will accept based on the blob's MIME type.
// MediaRecorder emits webm/opus on Chromium and mp4/aac on Safari, so we
// branch on the prefix and let the backend extension validation reject
// anything truly unsupported.
function inferFilenameFromBlob(blob: Blob): string {
  const type = (blob.type || "").toLowerCase();
  if (type.includes("webm")) return "recording.webm";
  if (type.includes("ogg")) return "recording.ogg";
  if (type.includes("mp4") || type.includes("aac")) return "recording.mp4";
  if (type.includes("wav")) return "recording.wav";
  if (type.includes("mpeg") || type.includes("mp3")) return "recording.mp3";
  // Fallback: webm is the most common Chromium output.
  return "recording.webm";
}

export function getAudioDownloadUrl(sessionId: string, queryId: string): string {
  return `${API_BASE_URL}/api/session/${sessionId}/query/${queryId}/audio/download`;
}

// Config endpoints
export async function getVoices(): Promise<VoicesResponse> {
  const response = await fetch(`${API_BASE_URL}/api/voices`);
  return handleResponse<VoicesResponse>(response);
}

export async function healthCheck(): Promise<HealthResponse> {
  const response = await fetch(`${API_BASE_URL}/api/health`);
  return handleResponse<HealthResponse>(response);
}

export { ApiError };

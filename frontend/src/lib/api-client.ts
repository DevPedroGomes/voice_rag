import type {
  SessionResponse,
  DocumentUploadResponse,
  DocumentListResponse,
  QueryRequest,
  QueryResponse,
  QueryHistoryResponse,
  VoicesResponse,
  HealthResponse,
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

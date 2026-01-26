// Voice options
export type VoiceType =
  | "alloy"
  | "ash"
  | "ballad"
  | "coral"
  | "echo"
  | "fable"
  | "onyx"
  | "nova"
  | "sage"
  | "shimmer"
  | "verse";

// Session
export interface SessionDocument {
  document_id: string;
  file_name: string;
  page_count: number;
  chunk_count: number;
  processed_at: string;
}

export interface SessionResponse {
  session_id: string;
  created_at: string;
  expires_at: string;
  documents: SessionDocument[];
  is_ready: boolean;
}

// Documents
export interface DocumentUploadResponse {
  document_id: string;
  file_name: string;
  page_count: number;
  chunk_count: number;
  processed_at: string;
  status: "processing" | "completed" | "error";
}

export interface DocumentListResponse {
  documents: SessionDocument[];
}

// Query
export interface QueryRequest {
  query: string;
  voice: VoiceType;
  stream_audio: boolean;
}

export interface SourceInfo {
  file_name: string;
  page_number: number | null;
  snippet: string;
}

export interface QueryResponse {
  query_id: string;
  text_response: string;
  sources: SourceInfo[];
  audio_stream_url: string | null;
  audio_download_url: string | null;
}

export interface QueryRecord {
  query_id: string;
  question: string;
  response: string;
  voice: string;
  sources: string[];
  created_at: string;
}

export interface QueryHistoryResponse {
  queries: QueryRecord[];
}

// Voices
export interface VoiceOption {
  id: VoiceType;
  name: string;
  description: string;
}

export interface VoicesResponse {
  voices: VoiceOption[];
}

// Health
export interface HealthResponse {
  status: "healthy" | "unhealthy";
  qdrant_connected: boolean;
}

// Audio streaming events
export interface AudioChunkEvent {
  chunk: string; // base64 encoded PCM
  index: number;
}

export interface AudioCompleteEvent {
  total_chunks: number;
}

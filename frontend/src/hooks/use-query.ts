"use client";

import { useState, useCallback } from "react";
import type { QueryResponse, VoiceType } from "@/types/api";
import { submitQuery, ApiError } from "@/lib/api-client";

interface UseQueryReturn {
  isLoading: boolean;
  error: string | null;
  response: QueryResponse | null;
  submit: (
    sessionId: string,
    query: string,
    voice: VoiceType,
    streamAudio?: boolean
  ) => Promise<QueryResponse | null>;
  clear: () => void;
}

export function useQuery(): UseQueryReturn {
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [response, setResponse] = useState<QueryResponse | null>(null);

  const submit = useCallback(
    async (
      sessionId: string,
      query: string,
      voice: VoiceType,
      streamAudio = true
    ): Promise<QueryResponse | null> => {
      setIsLoading(true);
      setError(null);

      try {
        const result = await submitQuery(sessionId, {
          query,
          voice,
          stream_audio: streamAudio,
        });
        setResponse(result);
        return result;
      } catch (err) {
        let message: string;
        if (err instanceof ApiError && err.status === 429) {
          message = "Query limit reached. Restart to create a new session.";
        } else {
          message = err instanceof Error ? err.message : "Query failed";
        }
        setError(message);
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    []
  );

  const clear = useCallback(() => {
    setResponse(null);
    setError(null);
  }, []);

  return {
    isLoading,
    error,
    response,
    submit,
    clear,
  };
}

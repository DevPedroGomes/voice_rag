"use client";

import { useState, useEffect, useCallback } from "react";
import type { SessionResponse, SessionDocument } from "@/types/api";
import { createSession, getSession } from "@/lib/api-client";

const SESSION_KEY = "voice-rag-session-id";

interface UseSessionReturn {
  session: SessionResponse | null;
  sessionId: string | null;
  isLoading: boolean;
  error: string | null;
  documents: SessionDocument[];
  isReady: boolean;
  refreshSession: () => Promise<void>;
  clearSession: () => void;
}

export function useSession(): UseSessionReturn {
  const [session, setSession] = useState<SessionResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const initSession = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      // Check for existing session in localStorage
      const storedSessionId = localStorage.getItem(SESSION_KEY);

      if (storedSessionId) {
        try {
          const existingSession = await getSession(storedSessionId);
          setSession(existingSession);
          setIsLoading(false);
          return;
        } catch {
          // Session expired or not found, create new one
          localStorage.removeItem(SESSION_KEY);
        }
      }

      // Create new session
      const newSession = await createSession();
      localStorage.setItem(SESSION_KEY, newSession.session_id);
      setSession(newSession);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to initialize session");
    } finally {
      setIsLoading(false);
    }
  }, []);

  const refreshSession = useCallback(async () => {
    if (!session?.session_id) return;

    try {
      const refreshedSession = await getSession(session.session_id);
      setSession(refreshedSession);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to refresh session");
    }
  }, [session?.session_id]);

  const clearSession = useCallback(() => {
    localStorage.removeItem(SESSION_KEY);
    setSession(null);
    initSession();
  }, [initSession]);

  useEffect(() => {
    initSession();
  }, [initSession]);

  return {
    session,
    sessionId: session?.session_id ?? null,
    isLoading,
    error,
    documents: session?.documents ?? [],
    isReady: session?.is_ready ?? false,
    refreshSession,
    clearSession,
  };
}

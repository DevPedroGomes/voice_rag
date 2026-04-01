"use client";

import { useState, useEffect, useCallback } from "react";
import type { SessionResponse, SessionDocument } from "@/types/api";
import { createSession, getSession } from "@/lib/api-client";

const SESSION_KEY = "voice-rag-session";
const SESSION_MAX_AGE_MS = 60 * 60 * 1000; // 1 hour client-side (server is source of truth)

interface UseSessionReturn {
  session: SessionResponse | null;
  sessionId: string | null;
  isLoading: boolean;
  error: string | null;
  documents: SessionDocument[];
  isReady: boolean;
  queriesRemaining: number;
  documentsRemaining: number;
  refreshSession: () => Promise<void>;
  clearSession: () => void;
}

function saveSession(id: string) {
  localStorage.setItem(SESSION_KEY, JSON.stringify({ id, ts: Date.now() }));
}

export function useSession(): UseSessionReturn {
  const [session, setSession] = useState<SessionResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const initSession = useCallback(async () => {
    setIsLoading(true);
    setError(null);

    try {
      const raw = localStorage.getItem(SESSION_KEY);
      // Migrate legacy key
      const legacyId = localStorage.getItem("voice-rag-session-id");
      if (legacyId) localStorage.removeItem("voice-rag-session-id");

      if (raw) {
        try {
          const { id, ts } = JSON.parse(raw);
          if (Date.now() - ts > SESSION_MAX_AGE_MS) {
            localStorage.removeItem(SESSION_KEY);
          } else {
            const existingSession = await getSession(id);
            saveSession(id); // refresh timestamp on successful load
            setSession(existingSession);
            setIsLoading(false);
            return;
          }
        } catch {
          // Session expired on server or parse error — create new silently
          localStorage.removeItem(SESSION_KEY);
        }
      }

      const newSession = await createSession();
      saveSession(newSession.session_id);
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
      saveSession(session.session_id); // refresh timestamp
      setSession(refreshedSession);
    } catch {
      // Session expired on server — create new one transparently
      localStorage.removeItem(SESSION_KEY);
      const newSession = await createSession();
      saveSession(newSession.session_id);
      setSession(newSession);
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
    queriesRemaining: session?.queries_remaining ?? 0,
    documentsRemaining: session?.documents_remaining ?? 0,
    refreshSession,
    clearSession,
  };
}

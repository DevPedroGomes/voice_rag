"use client";

import { useState, useCallback, useEffect } from "react";
import { toast } from "sonner";
import type { VoiceType, QueryRecord } from "@/types/api";
import { getAudioStreamUrl } from "@/lib/api-client";
import { useSession } from "@/hooks/use-session";
import { useDocuments } from "@/hooks/use-documents";
import { useQuery } from "@/hooks/use-query";
import { useAudioStream } from "@/hooks/use-audio-stream";
import { getQueryHistory } from "@/lib/api-client";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { PDFUpload } from "@/components/pdf-upload";
import { DocumentList } from "@/components/document-list";
import { VoiceSelector } from "@/components/voice-selector";
import { QueryInput } from "@/components/query-input";
import { QueryResponseCard } from "@/components/query-response";
import { ChatHistory } from "@/components/chat-history";

export default function Home() {
  const {
    session,
    sessionId,
    isLoading: sessionLoading,
    documents,
    isReady,
    refreshSession,
    clearSession,
  } = useSession();

  const { upload, isUploading, uploadError, deleteDocument } = useDocuments();
  const { submit, isLoading: queryLoading, response, error: queryError } = useQuery();
  const {
    isPlaying,
    isPaused,
    isLoading: audioLoading,
    play: playAudio,
    stop: stopAudio,
    togglePause,
  } = useAudioStream();

  const [selectedVoice, setSelectedVoice] = useState<VoiceType>("coral");
  const [queryHistory, setQueryHistory] = useState<QueryRecord[]>([]);

  // Load query history
  useEffect(() => {
    if (sessionId) {
      getQueryHistory(sessionId)
        .then((res) => setQueryHistory(res.queries))
        .catch(() => {});
    }
  }, [sessionId, response]);

  const handleUpload = useCallback(
    async (file: File) => {
      if (!sessionId) return;

      const result = await upload(sessionId, file);
      if (result) {
        toast.success(`Uploaded ${file.name}`);
        await refreshSession();
      } else {
        toast.error(uploadError || "Upload failed");
      }
    },
    [sessionId, upload, refreshSession, uploadError]
  );

  const handleDeleteDocument = useCallback(
    async (documentId: string) => {
      if (!sessionId) return;

      const success = await deleteDocument(sessionId, documentId);
      if (success) {
        toast.success("Document removed");
        await refreshSession();
      } else {
        toast.error("Failed to remove document");
      }
    },
    [sessionId, deleteDocument, refreshSession]
  );

  const handleQuery = useCallback(
    async (query: string) => {
      if (!sessionId) return;

      const result = await submit(sessionId, query, selectedVoice);
      if (result) {
        // Auto-play audio
        if (result.audio_stream_url) {
          playAudio(getAudioStreamUrl(sessionId, result.query_id));
        }
      } else {
        toast.error(queryError || "Query failed");
      }
    },
    [sessionId, selectedVoice, submit, playAudio, queryError]
  );

  const handlePlayAudio = useCallback(() => {
    if (!sessionId || !response?.query_id) return;
    playAudio(getAudioStreamUrl(sessionId, response.query_id));
  }, [sessionId, response, playAudio]);

  const handleRestart = useCallback(() => {
    stopAudio();
    setQueryHistory([]);
    clearSession();
    toast.success("Session restarted");
  }, [stopAudio, clearSession]);

  if (sessionLoading) {
    return (
      <main className="min-h-screen bg-gradient-to-b from-background to-muted/20">
        <div className="container max-w-4xl mx-auto py-12 px-4">
          <div className="space-y-6">
            <Skeleton className="h-12 w-64" />
            <Skeleton className="h-48 w-full" />
            <Skeleton className="h-32 w-full" />
          </div>
        </div>
      </main>
    );
  }

  return (
    <main className="min-h-screen bg-gradient-to-b from-background to-muted/20">
      <div className="container max-w-4xl mx-auto py-12 px-4">
        {/* Header */}
        <header className="mb-8">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div>
              <h1 className="text-2xl sm:text-3xl font-bold tracking-tight">
                Voice RAG
              </h1>
              <p className="text-muted-foreground mt-1 text-sm sm:text-base">
                Ask questions about your documents and get voice-powered answers
              </p>
            </div>
            <div className="flex items-center gap-2 shrink-0">
              {session && (
                <Badge variant="outline" className="text-xs">
                  Active
                </Badge>
              )}
              <Button
                variant="outline"
                size="sm"
                onClick={handleRestart}
                className="flex items-center gap-2"
              >
                <svg
                  className="w-4 h-4 shrink-0"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth={2}
                    d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"
                  />
                </svg>
Restart
              </Button>
            </div>
          </div>
        </header>

        <div className="grid gap-6 lg:grid-cols-3">
          {/* Sidebar */}
          <div className="lg:col-span-1 space-y-6">
            {/* Upload */}
            <Card className="p-4">
              <h2 className="text-sm font-medium mb-3">Upload Documents</h2>
              <PDFUpload
                onUpload={handleUpload}
                isUploading={isUploading}
                disabled={!sessionId}
              />
            </Card>

            {/* Documents */}
            <div>
              <h2 className="text-sm font-medium mb-3">Your Documents</h2>
              <DocumentList
                documents={documents}
                onDelete={handleDeleteDocument}
              />
            </div>

            {/* Voice Selector */}
            <Card className="p-4">
              <VoiceSelector
                value={selectedVoice}
                onChange={setSelectedVoice}
                disabled={queryLoading}
              />
            </Card>

            {/* Chat History */}
            {queryHistory.length > 0 && (
              <ChatHistory queries={queryHistory} />
            )}
          </div>

          {/* Main Content */}
          <div className="lg:col-span-2 space-y-6">
            {/* Query Input */}
            <Card className="p-6">
              <h2 className="text-lg font-semibold mb-4">Ask a Question</h2>
              <QueryInput
                onSubmit={handleQuery}
                isLoading={queryLoading}
                disabled={!isReady}
              />
              {!isReady && documents.length === 0 && (
                <p className="text-sm text-muted-foreground mt-3 text-center">
                  Upload a PDF to get started
                </p>
              )}
            </Card>

            {/* Response */}
            <QueryResponseCard
              response={response}
              isLoading={queryLoading}
              isAudioPlaying={isPlaying}
              isAudioPaused={isPaused}
              isAudioLoading={audioLoading}
              onPlayAudio={handlePlayAudio}
              onStopAudio={stopAudio}
              onTogglePause={togglePause}
            />
          </div>
        </div>

        {/* Footer */}
        <footer className="mt-12 text-center text-sm text-muted-foreground">
          <p>
            Built with Next.js, FastAPI, and OpenAI
          </p>
        </footer>
      </div>
    </main>
  );
}

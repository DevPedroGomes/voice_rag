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
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { PDFUpload } from "@/components/pdf-upload";
import { DocumentList } from "@/components/document-list";
import { VoiceSelector } from "@/components/voice-selector";
import { QueryInput } from "@/components/query-input";
import { QueryResponseCard } from "@/components/query-response";
import { ChatHistory } from "@/components/chat-history";
import { cn } from "@/lib/utils";
import { FileUp, Cpu, Search, MessageSquare as MsgIcon, Volume2 } from "lucide-react";

// ─── Pipeline Section (shown when no documents) ───

function PipelineSection() {
  const steps = [
    { icon: FileUp, title: "Upload PDF", desc: "Your document is split into semantic chunks using LangChain text splitters.", color: "bg-blue-50 text-blue-600" },
    { icon: Cpu, title: "Embed Locally", desc: "Each chunk is embedded using FastEmbed (BAAI/bge-small-en-v1.5) — no external API needed.", color: "bg-purple-50 text-purple-600" },
    { icon: Search, title: "Vector Search", desc: "Your question is embedded and matched against stored chunks via pgvector cosine similarity.", color: "bg-emerald-50 text-emerald-600" },
    { icon: MsgIcon, title: "AI Agent", desc: "A Processor Agent (GPT-4.1-mini) synthesizes a grounded answer from the retrieved context.", color: "bg-orange-50 text-orange-600" },
    { icon: Volume2, title: "Voice Response", desc: "The answer is streamed as speech via GPT-4o-mini-TTS using Server-Sent Events + Web Audio API.", color: "bg-pink-50 text-pink-600" },
  ];

  return (
    <div className="mb-6 animate-fade-in-up">
      <div className="flex items-center gap-3 mb-4">
        <span className="text-xs font-bold text-neutral-400 uppercase tracking-widest font-mono">How It Works</span>
        <div className="h-px flex-1 bg-neutral-200" />
      </div>
      <div className="grid gap-3 sm:grid-cols-5">
        {steps.map((step, i) => (
          <div key={step.title} className="bg-white border border-neutral-200 rounded-xl p-3 card-shadow">
            <div className="flex items-center gap-2 mb-2">
              <div className={`rounded-lg p-1.5 ${step.color}`}>
                <step.icon className="h-3.5 w-3.5" />
              </div>
              <span className="text-[10px] font-mono text-neutral-400">{i + 1}</span>
            </div>
            <h4 className="text-xs font-semibold text-neutral-900 mb-0.5">{step.title}</h4>
            <p className="text-[11px] text-neutral-500 leading-relaxed">{step.desc}</p>
          </div>
        ))}
      </div>
      <p className="text-[11px] text-neutral-400 font-mono text-center mt-3">
        FastEmbed (local) · PostgreSQL + pgvector · OpenAI Agents SDK · SSE Audio Streaming
      </p>
    </div>
  );
}

// ─── Step Card ───

function StepCard({
  number,
  title,
  subtitle,
  status,
  expanded,
  onToggle,
  disabled,
  children,
}: {
  number: number;
  title: string;
  subtitle?: string;
  status: "active" | "completed" | "locked";
  expanded: boolean;
  onToggle?: () => void;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  const isClickable = status === "completed" && onToggle;

  return (
    <div
      className={cn(
        "bg-white border rounded-2xl card-shadow transition-all duration-300",
        status === "locked" ? "opacity-50 border-neutral-100" : "border-neutral-200",
        expanded && status !== "locked" && "ring-1 ring-orange-200"
      )}
    >
      {/* Header */}
      <button
        type="button"
        className={cn(
          "w-full flex items-center gap-4 p-5 text-left",
          isClickable ? "cursor-pointer hover:bg-neutral-50 transition-colors rounded-2xl" : "cursor-default"
        )}
        onClick={isClickable ? onToggle : undefined}
        disabled={status === "locked"}
      >
        {/* Number badge */}
        <div
          className={cn(
            "flex items-center justify-center w-9 h-9 rounded-full text-sm font-semibold shrink-0 transition-colors",
            status === "completed" && "bg-emerald-100 text-emerald-700",
            status === "active" && "bg-orange-100 text-orange-700",
            status === "locked" && "bg-neutral-100 text-neutral-400"
          )}
        >
          {status === "completed" ? (
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
            </svg>
          ) : (
            number
          )}
        </div>

        {/* Title */}
        <div className="flex-1 min-w-0">
          <h3 className={cn(
            "text-sm font-semibold",
            status === "locked" ? "text-neutral-400" : "text-neutral-900"
          )}>
            {title}
          </h3>
          {subtitle && (
            <p className="text-xs text-neutral-400 mt-0.5">{subtitle}</p>
          )}
        </div>

        {/* Expand/collapse indicator */}
        {isClickable && (
          <svg
            className={cn(
              "w-4 h-4 text-neutral-400 transition-transform",
              expanded && "rotate-180"
            )}
            fill="none" stroke="currentColor" viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
          </svg>
        )}
      </button>

      {/* Content */}
      {expanded && status !== "locked" && (
        <div className={cn(
          "px-5 pb-5 animate-fade-in-up",
          disabled && "pointer-events-none opacity-60"
        )}>
          <div className="border-t border-neutral-100 pt-4">
            {children}
          </div>
        </div>
      )}
    </div>
  );
}

// ─── Main Page ───

export default function Home() {
  const {
    session,
    sessionId,
    isLoading: sessionLoading,
    documents,
    isReady,
    queriesRemaining,
    documentsRemaining,
    refreshSession,
    clearSession,
  } = useSession();

  const { upload, isUploading, uploadError, deleteDocument } = useDocuments();
  const { submit, isLoading: queryLoading, response, error: queryError } = useQuery();
  const {
    isPlaying,
    isPaused,
    isLoading: audioLoading,
    error: audioError,
    play: playAudio,
    stop: stopAudio,
    togglePause,
  } = useAudioStream();

  const [selectedVoice, setSelectedVoice] = useState<VoiceType>("coral");
  const [queryHistory, setQueryHistory] = useState<QueryRecord[]>([]);

  // Step expansion state
  const hasDocuments = documents.length > 0;
  const [step1Expanded, setStep1Expanded] = useState(true);
  const [step2Expanded, setStep2Expanded] = useState(false);

  // Auto-transition: when first document uploaded, collapse step 1 and open step 2/3
  useEffect(() => {
    if (hasDocuments) {
      setStep1Expanded(false);
      setStep2Expanded(false);
    } else {
      setStep1Expanded(true);
    }
  }, [hasDocuments]);

  // Load query history
  useEffect(() => {
    if (sessionId) {
      getQueryHistory(sessionId)
        .then((res) => setQueryHistory(res.queries))
        .catch(() => { toast.error("Falha ao carregar historico"); });
    }
  }, [sessionId]);

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
        if (result.audio_stream_url) {
          playAudio(getAudioStreamUrl(sessionId, result.query_id));
        }
        await refreshSession();
        getQueryHistory(sessionId)
          .then((res) => setQueryHistory(res.queries))
          .catch((err) => { console.error("Failed to refresh query history:", err); });
      } else {
        toast.error(queryError || "Query failed");
      }
    },
    [sessionId, selectedVoice, submit, playAudio, queryError, refreshSession]
  );

  const handlePlayAudio = useCallback(() => {
    if (!sessionId || !response?.query_id) return;
    playAudio(getAudioStreamUrl(sessionId, response.query_id));
  }, [sessionId, response, playAudio]);

  const handleRestart = useCallback(() => {
    stopAudio();
    setQueryHistory([]);
    clearSession();
    setStep1Expanded(true);
    setStep2Expanded(false);
    toast.success("Session restarted");
  }, [stopAudio, clearSession]);

  // ─── Loading state ───
  if (sessionLoading) {
    return (
      <main className="min-h-screen bg-[#fafafa]">
        <div className="sticky top-0 z-50 border-b border-neutral-200 bg-white/90 backdrop-blur-xl">
          <div className="max-w-3xl mx-auto px-6 sm:px-8 h-14 flex items-center">
            <Skeleton className="h-7 w-40" />
          </div>
        </div>
        <div className="max-w-3xl mx-auto py-10 px-6 sm:px-8 space-y-4">
          <Skeleton className="h-20 w-full rounded-2xl" />
          <Skeleton className="h-20 w-full rounded-2xl" />
          <Skeleton className="h-20 w-full rounded-2xl" />
        </div>
      </main>
    );
  }

  // Determine step statuses
  const step1Status = hasDocuments ? "completed" as const : "active" as const;
  const step2Status = hasDocuments ? "completed" as const : "locked" as const;
  const step3Status = isReady ? "active" as const : "locked" as const;

  // Busy state: prevent conflicting actions
  const isBusy = isUploading || queryLoading;

  return (
    <main className="min-h-screen bg-[#fafafa]">
      {/* Header */}
      <header className="sticky top-0 z-50 border-b border-neutral-200 bg-white/90 backdrop-blur-xl">
        <div className="max-w-3xl mx-auto px-6 sm:px-8 h-14 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <img src="/logo.png" alt="Logo" className="h-8 w-8 rounded-lg object-cover" />
            <span className="font-semibold tracking-tight text-neutral-900">Voice RAG</span>
          </div>
          <div className="flex items-center gap-2">
            {session && (
              <span className="text-xs text-neutral-400 font-mono hidden sm:inline">
                {queriesRemaining} queries · {documentsRemaining} docs left
              </span>
            )}
            <Button variant="outline" size="sm" onClick={handleRestart} className="text-xs">
              Restart
            </Button>
          </div>
        </div>
      </header>

      {/* Steps */}
      <div className="max-w-3xl mx-auto px-6 sm:px-8 py-8 space-y-4">

        {/* Welcome + Pipeline (only when no documents) */}
        {!hasDocuments && (
          <>
            <div className="text-center pb-6 animate-fade-in-up">
              <h2 className="text-2xl font-semibold tracking-tight text-neutral-900">
                Voice-Powered Document Q&A
              </h2>
              <p className="text-neutral-500 mt-2 text-sm max-w-md mx-auto">
                Upload a PDF, choose a voice, and ask questions — get spoken answers grounded in your documents.
              </p>
            </div>
            <PipelineSection />
          </>
        )}

        {/* Step 1: Upload Documents */}
        <StepCard
          number={1}
          title="Upload Documents"
          subtitle={hasDocuments ? `${documents.length} document${documents.length > 1 ? "s" : ""} indexed` : "PDF files up to 50MB"}
          status={step1Status}
          expanded={step1Expanded}
          onToggle={() => setStep1Expanded(!step1Expanded)}
          disabled={queryLoading}
        >
          <div className="space-y-4">
            <PDFUpload
              onUpload={handleUpload}
              isUploading={isUploading}
              disabled={!sessionId || documentsRemaining <= 0 || queryLoading}
            />
            {documentsRemaining <= 0 && (
              <p className="text-xs text-neutral-400 text-center">Document limit reached</p>
            )}
            {documents.length > 0 && (
              <div className="pt-2">
                <DocumentList documents={documents} onDelete={handleDeleteDocument} />
              </div>
            )}
          </div>
        </StepCard>

        {/* Step 2: Select Voice */}
        <StepCard
          number={2}
          title="Select Voice"
          subtitle={hasDocuments ? selectedVoice.charAt(0).toUpperCase() + selectedVoice.slice(1) : "Choose how the AI responds"}
          status={step2Status}
          expanded={step2Expanded}
          onToggle={hasDocuments ? () => setStep2Expanded(!step2Expanded) : undefined}
          disabled={queryLoading}
        >
          <VoiceSelector
            value={selectedVoice}
            onChange={setSelectedVoice}
            disabled={queryLoading}
          />
        </StepCard>

        {/* Step 3: Ask a Question */}
        <StepCard
          number={3}
          title="Ask a Question"
          subtitle={isReady ? "Type your question and press Enter" : "Complete the steps above first"}
          status={step3Status}
          expanded={isReady}
        >
          <div className="space-y-4">
            <QueryInput
              onSubmit={handleQuery}
              isLoading={queryLoading}
              disabled={!isReady || queriesRemaining <= 0 || isUploading}
            />
            {queriesRemaining <= 0 && (
              <p className="text-sm text-destructive text-center">
                Query limit reached. Restart to create a new session.
              </p>
            )}
          </div>
        </StepCard>

        {/* Response (appears after query) */}
        {(response || queryLoading) && (
          <div className="animate-fade-in-up">
            <QueryResponseCard
              response={response}
              isLoading={queryLoading}
              isAudioPlaying={isPlaying}
              isAudioPaused={isPaused}
              isAudioLoading={audioLoading}
              onPlayAudio={handlePlayAudio}
              onStopAudio={stopAudio}
              onTogglePause={togglePause}
              audioError={audioError}
            />
          </div>
        )}

        {/* Chat History */}
        {queryHistory.length > 0 && (
          <div className="animate-fade-in-up">
            <ChatHistory queries={queryHistory} />
          </div>
        )}

        {/* Footer */}
        <footer className="pt-8 pb-4 text-center text-sm text-neutral-400">
          Built with Next.js, FastAPI, and OpenAI
        </footer>
      </div>
    </main>
  );
}

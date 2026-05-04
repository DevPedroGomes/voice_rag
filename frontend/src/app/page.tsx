"use client";

import { useState, useCallback, useEffect } from "react";
import { toast } from "sonner";
import type { VoiceType, QueryRecord } from "@/types/api";
import { getAudioStreamUrl } from "@/lib/api-client";
import { useSession } from "@/hooks/use-session";
import { useDocuments } from "@/hooks/use-documents";
import { useQuery } from "@/hooks/use-query";
import { useAudioStream } from "@/hooks/use-audio-stream";
import { useLocale } from "@/hooks/use-locale";
import { getTranslations } from "@/lib/i18n";
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

function PipelineSection({ t }: { t: (key: string, params?: Record<string, string | number>) => string }) {
  const steps = [
    { icon: FileUp, title: t('pipeline.1.title'), desc: t('pipeline.1.desc'), color: "bg-blue-50 text-blue-600" },
    { icon: Cpu, title: t('pipeline.2.title'), desc: t('pipeline.2.desc'), color: "bg-purple-50 text-purple-600" },
    { icon: Search, title: t('pipeline.3.title'), desc: t('pipeline.3.desc'), color: "bg-emerald-50 text-emerald-600" },
    { icon: MsgIcon, title: t('pipeline.4.title'), desc: t('pipeline.4.desc'), color: "bg-orange-50 text-orange-600" },
    { icon: Volume2, title: t('pipeline.5.title'), desc: t('pipeline.5.desc'), color: "bg-pink-50 text-pink-600" },
  ];

  return (
    <div className="mb-6 animate-fade-in-up">
      <div className="flex items-center gap-3 mb-4">
        <span className="text-xs font-bold text-neutral-400 uppercase tracking-widest font-mono">{t('pipeline.label')}</span>
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
        {t('pipeline.footer')}
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

  const { locale, changeLocale } = useLocale();
  const t = getTranslations(locale);

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
        .catch(() => { toast.error(t('toast.historyFailed')); });
    }
  }, [sessionId]);

  const handleUpload = useCallback(
    async (file: File) => {
      if (!sessionId) return;

      const result = await upload(sessionId, file);
      if (result) {
        toast.success(t('toast.uploaded', { name: file.name }));
        await refreshSession();
      } else {
        toast.error(uploadError || t('toast.uploadFailed'));
      }
    },
    [sessionId, upload, refreshSession, uploadError]
  );

  const handleDeleteDocument = useCallback(
    async (documentId: string) => {
      if (!sessionId) return;

      const success = await deleteDocument(sessionId, documentId);
      if (success) {
        toast.success(t('toast.docRemoved'));
        await refreshSession();
      } else {
        toast.error(t('toast.docRemoveFailed'));
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
        toast.error(queryError || t('toast.queryFailed'));
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
    toast.success(t('toast.restarted'));
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

  // Step 1 subtitle
  const step1Subtitle = !hasDocuments
    ? t('step1.subtitle.empty')
    : documents.length === 1
      ? t('step1.subtitle.one')
      : t('step1.subtitle.many', { count: documents.length });

  return (
    <main className="min-h-screen bg-[#fafafa]">
      {/* Header */}
      <header className="sticky top-0 z-50 border-b border-neutral-200 bg-white/90 backdrop-blur-xl">
        <div className="max-w-3xl mx-auto px-6 sm:px-8 h-14 flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <img src="/logo.png" alt="Logo" className="h-8 w-8 rounded-lg object-cover" />
            <span className="font-semibold tracking-tight text-neutral-900">{t('nav.title')}</span>
          </div>
          <div className="flex items-center gap-2">
            {session && (
              <span className="text-xs text-neutral-400 font-mono hidden sm:inline">
                {queriesRemaining} {t('nav.queries')} · {documentsRemaining} {t('nav.docsLeft')}
              </span>
            )}
            {/* Language toggle */}
            <div className="flex items-center text-xs font-mono text-neutral-400 border border-neutral-200 rounded-md overflow-hidden">
              <button
                type="button"
                onClick={() => changeLocale('en')}
                className={cn(
                  "px-1.5 py-1 transition-colors",
                  locale === 'en' ? "bg-neutral-900 text-white" : "hover:bg-neutral-100"
                )}
              >
                EN
              </button>
              <button
                type="button"
                onClick={() => changeLocale('pt')}
                className={cn(
                  "px-1.5 py-1 transition-colors",
                  locale === 'pt' ? "bg-neutral-900 text-white" : "hover:bg-neutral-100"
                )}
              >
                PT
              </button>
            </div>
            <Button variant="outline" size="sm" onClick={handleRestart} className="text-xs">
              {t('nav.restart')}
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
                {t('welcome.title')}
              </h2>
              <p className="text-neutral-500 mt-2 text-sm max-w-md mx-auto">
                {t('welcome.subtitle')}
              </p>
            </div>
            <PipelineSection t={t} />
          </>
        )}

        {/* Step 1: Upload Documents */}
        <StepCard
          number={1}
          title={t('step1.title')}
          subtitle={step1Subtitle}
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
              <p className="text-xs text-neutral-400 text-center">{t('step1.limitReached')}</p>
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
          title={t('step2.title')}
          subtitle={hasDocuments ? selectedVoice.charAt(0).toUpperCase() + selectedVoice.slice(1) : t('step2.subtitle.locked')}
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
          title={t('step3.title')}
          subtitle={isReady ? t('step3.subtitle.ready') : t('step3.subtitle.locked')}
          status={step3Status}
          expanded={isReady}
        >
          <div className="space-y-4">
            <QueryInput
              onSubmit={handleQuery}
              isLoading={queryLoading}
              disabled={!isReady || queriesRemaining <= 0 || isUploading}
              sessionId={sessionId}
            />
            {queriesRemaining <= 0 && (
              <p className="text-sm text-destructive text-center">
                {t('step3.queryLimit')}
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
          {t('footer')}
        </footer>
      </div>
    </main>
  );
}

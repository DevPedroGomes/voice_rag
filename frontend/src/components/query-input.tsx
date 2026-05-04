"use client";

import { useEffect, useState } from "react";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { useAudioRecorder } from "@/hooks/use-audio-recorder";
import { transcribeAudio } from "@/lib/api-client";

interface QueryInputProps {
  onSubmit: (query: string) => void;
  isLoading: boolean;
  disabled?: boolean;
  /** Sprint 3.2 — required for the mic button to know which session to bill. */
  sessionId?: string | null;
}

export function QueryInput({
  onSubmit,
  isLoading,
  disabled,
  sessionId,
}: QueryInputProps) {
  const [query, setQuery] = useState("");
  const [transcribing, setTranscribing] = useState(false);
  const [transcriptionError, setTranscriptionError] = useState<string | null>(
    null
  );

  const recorder = useAudioRecorder({ maxDurationSeconds: 60 });

  // When the recorder finishes, ship the blob to /transcribe and dump the
  // result into the textarea so the user can review/edit before submitting.
  useEffect(() => {
    if (recorder.status !== "ready" || !recorder.blob) return;
    if (!sessionId) {
      setTranscriptionError("No active session.");
      recorder.reset();
      return;
    }

    let cancelled = false;
    const send = async () => {
      setTranscribing(true);
      setTranscriptionError(null);
      try {
        const result = await transcribeAudio(sessionId, recorder.blob!);
        if (cancelled) return;
        // Append (don't overwrite) — preserves anything the user already typed.
        setQuery((prev) => (prev ? `${prev} ${result.text}` : result.text));
      } catch (e) {
        if (cancelled) return;
        const message =
          e instanceof Error ? e.message : "Transcription failed.";
        setTranscriptionError(message);
      } finally {
        if (!cancelled) {
          setTranscribing(false);
          recorder.reset();
        }
      }
    };

    void send();
    return () => {
      cancelled = true;
    };
    // recorder.reset is stable; we only want to react to status/blob changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [recorder.status, recorder.blob, sessionId]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (query.trim() && !isLoading && !disabled) {
      onSubmit(query.trim());
      setQuery("");
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit(e);
    }
  };

  const handleMicClick = () => {
    if (recorder.status === "recording") {
      recorder.stop();
    } else {
      setTranscriptionError(null);
      void recorder.start();
    }
  };

  const isRecording = recorder.status === "recording";
  const isBusy = isLoading || transcribing || disabled;
  const micDisabled =
    !sessionId ||
    disabled ||
    isLoading ||
    transcribing ||
    recorder.status === "requesting-permission" ||
    recorder.status === "processing";

  // Format mm:ss for the timer; falls back to 0:00 when idle.
  const seconds = recorder.elapsedSeconds;
  const timerLabel = `${Math.floor(seconds / 60)}:${(seconds % 60)
    .toString()
    .padStart(2, "0")}`;

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      <Textarea
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder={
          disabled
            ? "Upload a document first..."
            : isRecording
            ? "Listening..."
            : transcribing
            ? "Transcribing audio..."
            : "Ask a question about your documents — type or use the microphone."
        }
        disabled={isBusy || isRecording}
        className="min-h-[80px] resize-none"
      />

      {(transcriptionError || recorder.error) && (
        <p className="text-xs text-red-500" role="alert">
          {transcriptionError || recorder.error}
        </p>
      )}

      <div className="flex items-center gap-2">
        <Button
          type="button"
          variant={isRecording ? "destructive" : "outline"}
          onClick={handleMicClick}
          disabled={micDisabled}
          aria-label={isRecording ? "Stop recording" : "Start recording"}
          aria-pressed={isRecording}
          className="flex items-center gap-2"
        >
          {isRecording ? (
            <>
              {/* Stop square icon */}
              <svg
                className="w-4 h-4"
                fill="currentColor"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <rect x="6" y="6" width="12" height="12" rx="1" />
              </svg>
              <span>{timerLabel}</span>
              {/* Live peak indicator: width scales with recorder.peak */}
              <span
                aria-hidden="true"
                className="inline-block h-2 w-12 rounded bg-red-200 overflow-hidden"
              >
                <span
                  className="block h-full bg-red-600 transition-all duration-75"
                  style={{
                    width: `${Math.min(100, Math.round(recorder.peak * 100))}%`,
                  }}
                />
              </span>
            </>
          ) : transcribing ? (
            <>
              <svg
                className="animate-spin h-4 w-4"
                fill="none"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                />
              </svg>
              <span>Transcribing</span>
            </>
          ) : (
            <>
              {/* Microphone icon */}
              <svg
                className="w-4 h-4"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
                aria-hidden="true"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M19 11a7 7 0 01-14 0m7 7v4m-4 0h8M12 1a3 3 0 00-3 3v8a3 3 0 006 0V4a3 3 0 00-3-3z"
                />
              </svg>
              <span>Speak</span>
            </>
          )}
        </Button>

        <Button
          type="submit"
          className="flex-1"
          disabled={!query.trim() || isBusy || isRecording}
        >
          {isLoading ? (
            <span className="flex items-center gap-2">
              <svg
                className="animate-spin h-4 w-4"
                fill="none"
                viewBox="0 0 24 24"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                />
              </svg>
              Processing...
            </span>
          ) : (
            <span className="flex items-center gap-2">
              <svg
                className="w-4 h-4"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
              Ask Question
            </span>
          )}
        </Button>
      </div>
    </form>
  );
}

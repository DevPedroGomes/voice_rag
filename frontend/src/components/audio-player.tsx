"use client";

import { Button } from "@/components/ui/button";

interface AudioPlayerProps {
  isPlaying: boolean;
  isPaused: boolean;
  isLoading: boolean;
  onPlay: () => void;
  onStop: () => void;
  onTogglePause: () => void;
  downloadUrl?: string | null;
}

export function AudioPlayer({
  isPlaying,
  isPaused,
  isLoading,
  onPlay,
  onStop,
  onTogglePause,
  downloadUrl,
}: AudioPlayerProps) {
  return (
    <div className="flex flex-wrap items-center gap-2">
      {/* Play/Stop Button */}
      <Button
        variant={isPlaying && !isPaused ? "destructive" : "default"}
        size="sm"
        onClick={isPlaying ? onStop : onPlay}
        disabled={isLoading}
        className="flex items-center gap-1.5 min-w-0"
      >
        {isLoading ? (
          <>
            <svg
              className="animate-spin h-4 w-4 shrink-0"
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
            <span className="hidden sm:inline">Loading...</span>
          </>
        ) : isPlaying ? (
          <>
            <svg
              className="w-4 h-4 shrink-0"
              fill="currentColor"
              viewBox="0 0 24 24"
            >
              <rect x="6" y="4" width="4" height="16" />
              <rect x="14" y="4" width="4" height="16" />
            </svg>
            <span>Stop</span>
          </>
        ) : (
          <>
            <svg
              className="w-4 h-4 shrink-0"
              fill="currentColor"
              viewBox="0 0 24 24"
            >
              <path d="M8 5v14l11-7z" />
            </svg>
            <span className="hidden sm:inline">Play</span>
          </>
        )}
      </Button>

      {/* Pause/Resume Button - always show when playing */}
      {isPlaying && (
        <Button
          variant="outline"
          size="sm"
          onClick={onTogglePause}
          className="flex items-center gap-1.5 min-w-0"
        >
          {isPaused ? (
            <>
              <svg
                className="w-4 h-4 shrink-0"
                fill="currentColor"
                viewBox="0 0 24 24"
              >
                <path d="M8 5v14l11-7z" />
              </svg>
              <span className="hidden sm:inline">Resume</span>
            </>
          ) : (
            <>
              <svg
                className="w-4 h-4 shrink-0"
                fill="currentColor"
                viewBox="0 0 24 24"
              >
                <rect x="6" y="4" width="4" height="16" />
                <rect x="14" y="4" width="4" height="16" />
              </svg>
              <span className="hidden sm:inline">Pause</span>
            </>
          )}
        </Button>
      )}

      {downloadUrl && (
        <Button variant="outline" size="sm" asChild className="min-w-0">
          <a href={downloadUrl} download className="flex items-center gap-1.5">
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
                d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"
              />
            </svg>
            <span className="hidden sm:inline">Download</span>
          </a>
        </Button>
      )}
    </div>
  );
}

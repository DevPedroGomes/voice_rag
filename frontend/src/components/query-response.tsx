"use client";

import type { QueryResponse } from "@/types/api";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { AudioPlayer } from "./audio-player";

interface QueryResponseProps {
  response: QueryResponse | null;
  isLoading: boolean;
  isAudioPlaying: boolean;
  isAudioPaused: boolean;
  isAudioLoading: boolean;
  onPlayAudio: () => void;
  onStopAudio: () => void;
  onTogglePause: () => void;
  audioError?: string | null;
}

export function QueryResponseCard({
  response,
  isLoading,
  isAudioPlaying,
  isAudioPaused,
  isAudioLoading,
  onPlayAudio,
  onStopAudio,
  onTogglePause,
  audioError,
}: QueryResponseProps) {
  if (isLoading) {
    return (
      <Card className="p-6 space-y-4">
        <Skeleton className="h-4 w-3/4" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-5/6" />
        <Skeleton className="h-4 w-2/3" />
      </Card>
    );
  }

  if (!response) {
    return null;
  }

  return (
    <Card className="p-6 space-y-4">
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
        <h3 className="font-semibold text-lg">Response</h3>
        <AudioPlayer
          isPlaying={isAudioPlaying}
          isPaused={isAudioPaused}
          isLoading={isAudioLoading}
          onPlay={onPlayAudio}
          onStop={onStopAudio}
          onTogglePause={onTogglePause}
          downloadUrl={response.audio_download_url}
        />
      </div>

      {audioError && (
        <p className="text-sm text-destructive mt-2">{audioError}</p>
      )}

      <div className="prose prose-sm dark:prose-invert max-w-none">
        <p className="whitespace-pre-wrap">{response.text_response}</p>
      </div>

      {response.sources.length > 0 && (
        <div className="pt-4 border-t space-y-2">
          <h4 className="text-sm font-medium text-muted-foreground">Sources</h4>
          <div className="flex flex-wrap gap-2">
            {response.sources.map((source, index) => (
              <Badge key={index} variant="outline" className="text-xs">
                {source.file_name}
                {source.page_number && ` (p.${source.page_number})`}
              </Badge>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}

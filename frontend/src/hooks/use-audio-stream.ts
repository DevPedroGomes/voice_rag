"use client";

import { useState, useCallback, useRef } from "react";
import { streamAudio, AudioStreamPlayer } from "@/lib/audio-context";

interface UseAudioStreamReturn {
  isPlaying: boolean;
  isPaused: boolean;
  isLoading: boolean;
  chunksReceived: number;
  error: string | null;
  play: (streamUrl: string) => Promise<void>;
  stop: () => void;
  togglePause: () => Promise<void>;
}

export function useAudioStream(): UseAudioStreamReturn {
  const [isPlaying, setIsPlaying] = useState(false);
  const [isPaused, setIsPaused] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [chunksReceived, setChunksReceived] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const playerRef = useRef<AudioStreamPlayer | null>(null);

  const play = useCallback(async (streamUrl: string) => {
    setIsLoading(true);
    setIsPlaying(false);
    setIsPaused(false);
    setChunksReceived(0);
    setError(null);

    try {
      playerRef.current = await streamAudio(
        streamUrl,
        (index) => {
          setChunksReceived(index + 1);
          if (index === 0) {
            setIsLoading(false);
            setIsPlaying(true);
          }
        },
        () => {
          setIsPlaying(false);
          setIsPaused(false);
        },
        (err) => {
          setError(err);
          setIsPlaying(false);
          setIsPaused(false);
          setIsLoading(false);
        },
        (paused) => {
          setIsPaused(paused);
        }
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to start audio");
      setIsLoading(false);
    }
  }, []);

  const stop = useCallback(() => {
    if (playerRef.current) {
      playerRef.current.stop();
      playerRef.current = null;
    }
    setIsPlaying(false);
    setIsPaused(false);
    setIsLoading(false);
  }, []);

  const togglePause = useCallback(async () => {
    if (playerRef.current) {
      await playerRef.current.togglePause();
    }
  }, []);

  return {
    isPlaying,
    isPaused,
    isLoading,
    chunksReceived,
    error,
    play,
    stop,
    togglePause,
  };
}

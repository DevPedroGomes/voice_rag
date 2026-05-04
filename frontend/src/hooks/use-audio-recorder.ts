"use client";

/**
 * Sprint 3.2 — Browser audio recorder hook.
 *
 * Wraps MediaRecorder + getUserMedia into a tiny state machine that the
 * UI can drive with start/stop. Returns the recorded Blob (and a cheap
 * peak-amplitude signal for a waveform indicator) so the caller can
 * pipe it into the /transcribe endpoint.
 *
 * Why a custom hook (and not a library):
 *  - Zero new deps; MediaRecorder is in every modern browser.
 *  - Lets us pick the right MIME (webm/opus on Chromium, mp4/aac on Safari)
 *    explicitly, which Whisper requires.
 *  - Cleans up streams reliably even when the component unmounts mid-
 *    recording (a common React 18 strict-mode footgun).
 *
 * State machine:
 *   idle ──start()──▶ recording ──stop()──▶ ready ──reset()──▶ idle
 *           │                   │
 *           └──▶ error ◀────────┘
 */

import { useCallback, useEffect, useRef, useState } from "react";

export type RecorderStatus =
  | "idle"
  | "requesting-permission"
  | "recording"
  | "processing"
  | "ready"
  | "error";

export interface UseAudioRecorderOptions {
  /** Hard cap in seconds. Past this, recording auto-stops. */
  maxDurationSeconds?: number;
}

export interface UseAudioRecorderReturn {
  status: RecorderStatus;
  /** Last error message, if any. Cleared on next start(). */
  error: string | null;
  /** Final recorded blob, populated when status === 'ready'. */
  blob: Blob | null;
  /** Recording elapsed time in seconds (live updating). */
  elapsedSeconds: number;
  /** Live peak amplitude in [0, 1] for a waveform indicator. */
  peak: number;
  start: () => Promise<void>;
  stop: () => void;
  reset: () => void;
}

const DEFAULT_MAX_DURATION = 60;

/**
 * Pick the first MediaRecorder mime type the current browser supports.
 * Order matters — Whisper handles all of these, but we prefer webm/opus
 * on Chromium for the best compression and lowest upload cost.
 */
function pickSupportedMimeType(): string | undefined {
  if (typeof MediaRecorder === "undefined") return undefined;
  const candidates = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/ogg;codecs=opus",
    "audio/mp4;codecs=mp4a.40.2", // Safari (AAC)
    "audio/mp4",
  ];
  for (const candidate of candidates) {
    if (MediaRecorder.isTypeSupported(candidate)) return candidate;
  }
  return undefined;
}

export function useAudioRecorder(
  options: UseAudioRecorderOptions = {}
): UseAudioRecorderReturn {
  const maxDuration = options.maxDurationSeconds ?? DEFAULT_MAX_DURATION;

  const [status, setStatus] = useState<RecorderStatus>("idle");
  const [error, setError] = useState<string | null>(null);
  const [blob, setBlob] = useState<Blob | null>(null);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [peak, setPeak] = useState(0);

  // Refs for objects that don't belong in state (mutable, not rendered).
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const rafRef = useRef<number | null>(null);
  const startedAtRef = useRef<number>(0);
  const tickIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const autoStopTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  /** Tear down all media + audio resources. Safe to call multiple times. */
  const cleanup = useCallback(() => {
    if (rafRef.current !== null) {
      cancelAnimationFrame(rafRef.current);
      rafRef.current = null;
    }
    if (tickIntervalRef.current !== null) {
      clearInterval(tickIntervalRef.current);
      tickIntervalRef.current = null;
    }
    if (autoStopTimeoutRef.current !== null) {
      clearTimeout(autoStopTimeoutRef.current);
      autoStopTimeoutRef.current = null;
    }
    if (analyserRef.current) {
      try {
        analyserRef.current.disconnect();
      } catch {
        /* ignore */
      }
      analyserRef.current = null;
    }
    if (audioContextRef.current && audioContextRef.current.state !== "closed") {
      audioContextRef.current.close().catch(() => {
        /* ignore */
      });
    }
    audioContextRef.current = null;
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track: MediaStreamTrack) => track.stop());
      streamRef.current = null;
    }
    mediaRecorderRef.current = null;
    setPeak(0);
  }, []);

  // Strict-mode safe: ensure cleanup if the consumer unmounts mid-recording.
  useEffect(() => {
    return cleanup;
  }, [cleanup]);

  const start = useCallback(async () => {
    setError(null);
    setBlob(null);
    setElapsedSeconds(0);
    setPeak(0);
    chunksRef.current = [];

    if (
      typeof navigator === "undefined" ||
      !navigator.mediaDevices ||
      !navigator.mediaDevices.getUserMedia
    ) {
      setStatus("error");
      setError("Microphone access is not available in this browser.");
      return;
    }

    setStatus("requesting-permission");

    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          // Modest defaults — Whisper accepts any sample rate but 16k is
          // both bandwidth-friendly and sufficient for speech recognition.
          channelCount: 1,
          sampleRate: 16000,
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      });
    } catch (e) {
      const message =
        e instanceof Error
          ? e.message
          : "Microphone permission was denied.";
      setStatus("error");
      setError(message);
      return;
    }

    streamRef.current = stream;
    const mimeType = pickSupportedMimeType();

    let recorder: MediaRecorder;
    try {
      recorder = mimeType
        ? new MediaRecorder(stream, { mimeType })
        : new MediaRecorder(stream);
    } catch (e) {
      cleanup();
      setStatus("error");
      setError(
        e instanceof Error
          ? `Failed to start recorder: ${e.message}`
          : "Failed to start recorder."
      );
      return;
    }

    mediaRecorderRef.current = recorder;

    recorder.ondataavailable = (event: BlobEvent) => {
      if (event.data && event.data.size > 0) {
        chunksRef.current.push(event.data);
      }
    };

    recorder.onstop = () => {
      // Build the final blob with the same MIME the recorder used so the
      // backend's extension inference picks the right Whisper decoder.
      const finalType = recorder.mimeType || mimeType || "audio/webm";
      const finalBlob = new Blob(chunksRef.current, { type: finalType });
      chunksRef.current = [];
      cleanup();
      setBlob(finalBlob);
      setStatus("ready");
    };

    recorder.onerror = (event: Event) => {
      cleanup();
      setStatus("error");
      setError(`Recorder error: ${(event as ErrorEvent).message ?? "unknown"}`);
    };

    // Spin up an analyser for the live peak indicator. Cheap (~1 FFT/frame).
    try {
      const audioContext = new AudioContext();
      audioContextRef.current = audioContext;
      const source = audioContext.createMediaStreamSource(stream);
      const analyser = audioContext.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      analyserRef.current = analyser;

      const buffer = new Uint8Array(analyser.frequencyBinCount);
      const tick = () => {
        if (!analyserRef.current) return;
        analyserRef.current.getByteTimeDomainData(buffer);
        // Center samples around 0 and find the largest absolute value.
        let max = 0;
        for (let i = 0; i < buffer.length; i++) {
          const v = Math.abs(buffer[i] - 128) / 128;
          if (v > max) max = v;
        }
        setPeak(max);
        rafRef.current = requestAnimationFrame(tick);
      };
      rafRef.current = requestAnimationFrame(tick);
    } catch {
      // Visual feedback is nice but not critical. Continue without it.
    }

    startedAtRef.current = Date.now();
    tickIntervalRef.current = setInterval(() => {
      const elapsed = Math.floor((Date.now() - startedAtRef.current) / 1000);
      setElapsedSeconds(elapsed);
    }, 250);

    autoStopTimeoutRef.current = setTimeout(() => {
      if (mediaRecorderRef.current && mediaRecorderRef.current.state === "recording") {
        mediaRecorderRef.current.stop();
      }
    }, maxDuration * 1000);

    recorder.start();
    setStatus("recording");
  }, [cleanup, maxDuration]);

  const stop = useCallback(() => {
    const recorder = mediaRecorderRef.current;
    if (!recorder || recorder.state !== "recording") return;
    setStatus("processing");
    try {
      recorder.stop();
    } catch {
      cleanup();
      setStatus("idle");
    }
  }, [cleanup]);

  const reset = useCallback(() => {
    cleanup();
    setStatus("idle");
    setError(null);
    setBlob(null);
    setElapsedSeconds(0);
    setPeak(0);
    chunksRef.current = [];
  }, [cleanup]);

  return {
    status,
    error,
    blob,
    elapsedSeconds,
    peak,
    start,
    stop,
    reset,
  };
}

const SAMPLE_RATE = 24000; // OpenAI TTS sample rate

export class AudioStreamPlayer {
  private audioContext: AudioContext | null = null;
  private eventSource: EventSource | null = null;
  private nextPlayTime = 0;
  private isPlaying = false;
  private isPaused = false;
  private onPlayingChange?: (playing: boolean) => void;
  private onPausedChange?: (paused: boolean) => void;

  constructor(
    onPlayingChange?: (playing: boolean) => void,
    onPausedChange?: (paused: boolean) => void
  ) {
    this.onPlayingChange = onPlayingChange;
    this.onPausedChange = onPausedChange;
  }

  setEventSource(es: EventSource): void {
    this.eventSource = es;
  }

  async start(): Promise<void> {
    if (!this.audioContext) {
      this.audioContext = new AudioContext({ sampleRate: SAMPLE_RATE });
    }

    if (this.audioContext.state === "suspended") {
      await this.audioContext.resume();
    }

    this.nextPlayTime = this.audioContext.currentTime;
    this.isPlaying = true;
    this.isPaused = false;
    this.onPlayingChange?.(true);
    this.onPausedChange?.(false);
  }

  async pause(): Promise<void> {
    if (this.audioContext && this.isPlaying && !this.isPaused) {
      await this.audioContext.suspend();
      this.isPaused = true;
      this.onPausedChange?.(true);
    }
  }

  async resume(): Promise<void> {
    if (this.audioContext && this.isPlaying && this.isPaused) {
      await this.audioContext.resume();
      this.isPaused = false;
      this.onPausedChange?.(false);
    }
  }

  async togglePause(): Promise<void> {
    if (this.isPaused) {
      await this.resume();
    } else {
      await this.pause();
    }
  }

  async playChunk(base64Chunk: string): Promise<void> {
    if (!this.audioContext || !this.isPlaying) return;

    // Decode base64 to typed arrays
    const binaryString = atob(base64Chunk);
    const bytes = Uint8Array.from(binaryString, (c) => c.charCodeAt(0));
    const int16Array = new Int16Array(bytes.buffer);
    const float32Array = Float32Array.from(int16Array, (s) => s / 32768.0);

    // Create audio buffer
    const audioBuffer = this.audioContext.createBuffer(
      1, // mono
      float32Array.length,
      SAMPLE_RATE
    );
    audioBuffer.getChannelData(0).set(float32Array);

    // Schedule playback
    const source = this.audioContext.createBufferSource();
    source.buffer = audioBuffer;
    source.connect(this.audioContext.destination);

    // Schedule at the next available time
    const startTime = Math.max(this.nextPlayTime, this.audioContext.currentTime);
    source.start(startTime);
    this.nextPlayTime = startTime + audioBuffer.duration;
  }

  stop(): void {
    this.isPlaying = false;
    this.isPaused = false;
    this.onPlayingChange?.(false);
    this.onPausedChange?.(false);

    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }

    if (this.audioContext) {
      this.audioContext.close();
      this.audioContext = null;
    }
  }

  get playing(): boolean {
    return this.isPlaying;
  }

  get paused(): boolean {
    return this.isPaused;
  }
}

export async function streamAudio(
  streamUrl: string,
  onChunk?: (index: number) => void,
  onComplete?: () => void,
  onError?: (error: string) => void,
  onPausedChange?: (paused: boolean) => void
): Promise<AudioStreamPlayer> {
  const player = new AudioStreamPlayer(undefined, onPausedChange);
  await player.start();

  const eventSource = new EventSource(streamUrl);
  player.setEventSource(eventSource);

  eventSource.addEventListener("audio_chunk", (event) => {
    try {
      const data = JSON.parse(event.data);
      player.playChunk(data.chunk);
      onChunk?.(data.index);
    } catch (e) {
      console.error("Error processing audio chunk:", e);
    }
  });

  eventSource.addEventListener("audio_complete", () => {
    eventSource.close();
    onComplete?.();
  });

  eventSource.addEventListener("error", (event) => {
    eventSource.close();
    player.stop();
    onError?.("Audio streaming error");
  });

  eventSource.onerror = () => {
    eventSource.close();
    player.stop();
    onError?.("Connection error");
  };

  return player;
}

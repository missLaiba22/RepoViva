import { SPEAKER_RATE, pcm16ToFloat } from "./pcm";

/** Plays a question's PCM16 24 kHz audio as it streams in, chunk after
 * chunk without gaps, and keeps it so the question can be replayed. */
export class QuestionPlayer {
  private context: AudioContext | null = null;
  private nextStart = 0;
  private rest: Uint8Array = new Uint8Array(0);
  private chunks: Float32Array[] = [];
  private sources = new Set<AudioBufferSourceNode>();

  private ctx(): AudioContext {
    this.context ??= new AudioContext();
    return this.context;
  }

  /** True when the browser blocked audio until the next tap (autoplay policy). */
  get blocked(): boolean {
    return this.context?.state === "suspended";
  }

  async unblock(): Promise<void> {
    await this.ctx().resume();
  }

  /** Start a new question: stop anything still playing and forget the last one. */
  reset(): void {
    this.stop();
    this.chunks = [];
    this.rest = new Uint8Array(0);
  }

  feed(data: ArrayBuffer): void {
    const joined = new Uint8Array(this.rest.length + data.byteLength);
    joined.set(this.rest);
    joined.set(new Uint8Array(data), this.rest.length);
    const { samples, rest } = pcm16ToFloat(joined);
    this.rest = rest;
    if (samples.length === 0) return;
    this.chunks.push(samples);
    this.schedule(samples);
  }

  /** Resolves when everything fed so far has finished playing. */
  async drained(): Promise<void> {
    const context = this.context;
    if (!context) return;
    const remaining = this.nextStart - context.currentTime;
    if (remaining > 0 && context.state === "running") {
      await new Promise((resolve) => setTimeout(resolve, remaining * 1000 + 50));
    }
  }

  /** Play the whole question again. Resolves when it's done. */
  async replay(): Promise<void> {
    this.stop();
    const context = this.ctx();
    await context.resume();
    for (const samples of this.chunks) this.schedule(samples);
    await this.drained();
  }

  stop(): void {
    for (const source of this.sources) {
      try {
        source.stop();
      } catch {
        // Already stopped.
      }
    }
    this.sources.clear();
    this.nextStart = 0;
  }

  close(): void {
    this.stop();
    void this.context?.close();
    this.context = null;
  }

  private schedule(samples: Float32Array): void {
    const context = this.ctx();
    const buffer = context.createBuffer(1, samples.length, SPEAKER_RATE);
    buffer.copyToChannel(samples as Float32Array<ArrayBuffer>, 0);
    const source = context.createBufferSource();
    source.buffer = buffer;
    source.connect(context.destination);
    // A small lead on the first chunk avoids a click if scheduling runs late.
    const start = Math.max(this.nextStart, context.currentTime + 0.03);
    source.start(start);
    this.nextStart = start + buffer.duration;
    this.sources.add(source);
    source.onended = () => this.sources.delete(source);
  }
}

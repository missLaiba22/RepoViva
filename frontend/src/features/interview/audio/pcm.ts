/** Pure PCM helpers. Voice Service speaks PCM16 little-endian mono:
 * 16 kHz from the client, 24 kHz to it (protocol v2). */

export const MIC_RATE = 16_000;
export const SPEAKER_RATE = 24_000;

/** Resample mono float audio from `fromRate` to `toRate` by averaging the
 * input samples each output sample covers. Averaging doubles as a crude
 * low-pass, which is enough for speech going to Whisper. */
export class Downsampler {
  private readonly ratio: number;
  private carry: Float32Array = new Float32Array(0);

  constructor(fromRate: number, toRate: number = MIC_RATE) {
    if (fromRate < toRate) throw new Error(`can't upsample from ${fromRate} to ${toRate}`);
    this.ratio = fromRate / toRate;
  }

  /** Feed the next block; returns the output samples it completes. Leftover
   * input is kept for the next call, so block boundaries don't click. */
  push(input: Float32Array): Float32Array {
    const samples = new Float32Array(this.carry.length + input.length);
    samples.set(this.carry);
    samples.set(input, this.carry.length);

    const count = Math.floor(samples.length / this.ratio);
    const out = new Float32Array(count);
    for (let i = 0; i < count; i++) {
      const start = Math.floor(i * this.ratio);
      const end = Math.floor((i + 1) * this.ratio);
      let sum = 0;
      for (let j = start; j < end; j++) sum += samples[j];
      out[i] = sum / (end - start);
    }
    this.carry = samples.slice(Math.floor(count * this.ratio));
    return out;
  }
}

/** Float [-1, 1] → PCM16 little-endian bytes. */
export function floatToPcm16(samples: Float32Array): ArrayBuffer {
  const buffer = new ArrayBuffer(samples.length * 2);
  const view = new DataView(buffer);
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return buffer;
}

/** PCM16 little-endian bytes → float [-1, 1]. Network frames needn't end on
 * a sample boundary, so an odd trailing byte is returned for the next frame. */
export function pcm16ToFloat(bytes: Uint8Array): { samples: Float32Array; rest: Uint8Array } {
  const usable = bytes.length - (bytes.length % 2);
  const view = new DataView(bytes.buffer, bytes.byteOffset, usable);
  const samples = new Float32Array(usable / 2);
  for (let i = 0; i < samples.length; i++) samples[i] = view.getInt16(i * 2, true) / 0x8000;
  return { samples, rest: bytes.slice(usable) };
}

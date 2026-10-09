import { describe, expect, it } from "vitest";
import { Downsampler, floatToPcm16, pcm16ToFloat } from "../src/features/interview/audio/pcm";

describe("Downsampler", () => {
  it("averages each group of input samples at an integer ratio", () => {
    const d = new Downsampler(48_000, 16_000);
    expect(Array.from(d.push(new Float32Array([0.3, 0.3, 0.3, -0.6, 0, 0])))).toEqual([
      expect.closeTo(0.3),
      expect.closeTo(-0.2),
    ]);
  });

  it("carries leftover input into the next block", () => {
    const d = new Downsampler(48_000, 16_000);
    expect(d.push(new Float32Array([1, 1, 1, 1])).length).toBe(1);
    expect(Array.from(d.push(new Float32Array([1, 1])))).toEqual([1]);
  });

  it("produces the right number of samples at a fractional ratio (44.1 kHz)", () => {
    const d = new Downsampler(44_100, 16_000);
    let total = 0;
    for (let i = 0; i < 100; i++) total += d.push(new Float32Array(441)).length;
    // 44,100 input samples = 1 s → 16,000 output samples, within one sample.
    expect(Math.abs(total - 16_000)).toBeLessThanOrEqual(1);
  });

  it("refuses to upsample", () => {
    expect(() => new Downsampler(8_000, 16_000)).toThrow();
  });
});

describe("PCM16 conversion", () => {
  it("encodes little-endian and clamps out-of-range samples", () => {
    const view = new DataView(floatToPcm16(new Float32Array([0, 1, -1, 2, -2, 0.5])));
    expect([0, 1, 2, 3, 4, 5].map((i) => view.getInt16(i * 2, true))).toEqual([0, 32767, -32768, 32767, -32768, 16383]);
  });

  it("round-trips through decoding", () => {
    const input = new Float32Array([0, 0.25, -0.5, 0.75]);
    const { samples, rest } = pcm16ToFloat(new Uint8Array(floatToPcm16(input)));
    expect(rest.length).toBe(0);
    samples.forEach((s, i) => expect(s).toBeCloseTo(input[i], 3));
  });

  it("holds back an odd trailing byte for the next frame", () => {
    const { samples, rest } = pcm16ToFloat(new Uint8Array([0x00, 0x40, 0x7f]));
    expect(samples.length).toBe(1);
    expect(samples[0]).toBeCloseTo(0.5);
    expect(Array.from(rest)).toEqual([0x7f]);
  });
});

import { MicError, type MicErrorKind } from "./microphone";
import { Downsampler, MIC_RATE, floatToPcm16 } from "./pcm";

/** Sent every ~100 ms while recording, like the terminal client (MIC_BLOCK). */
const CHUNK_SAMPLES = MIC_RATE / 10;

// The worklet only copies the mic's frames to the main thread; resampling
// and PCM conversion happen there, in plain testable code (pcm.ts).
const WORKLET = `
class Forward extends AudioWorkletProcessor {
  process(inputs) {
    const channel = inputs[0] && inputs[0][0];
    if (channel) this.port.postMessage(channel.slice(0));
    return true;
  }
}
registerProcessor("repoviva-forward", Forward);
`;

export interface Capture {
  /** Current input level, 0–1, for the meter. */
  level(): number;
  /** Start delivering PCM16 16 kHz chunks to `onChunk`. */
  record(onChunk: (pcm: ArrayBuffer) => void): void;
  /** Stop delivering and flush what's buffered. The mic stays open. */
  pause(): void;
  close(): void;
}

/** Open the microphone once for the whole interview. Recording is toggled
 * with record()/pause(), so each answer starts instantly. */
export async function openCapture(deviceId?: string): Promise<Capture> {
  let stream: MediaStream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        deviceId: deviceId ? { ideal: deviceId } : undefined,
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
  } catch (error) {
    const name = error instanceof DOMException ? error.name : "";
    const kind: MicErrorKind = name === "NotAllowedError" ? "denied" : name === "NotFoundError" ? "not-found" : "busy";
    throw new MicError(kind);
  }

  const context = new AudioContext();
  const url = URL.createObjectURL(new Blob([WORKLET], { type: "application/javascript" }));
  try {
    await context.audioWorklet.addModule(url);
  } finally {
    URL.revokeObjectURL(url);
  }

  const source = context.createMediaStreamSource(stream);
  const analyser = context.createAnalyser();
  analyser.fftSize = 1024;
  const levelSamples = new Float32Array(analyser.fftSize);
  const node = new AudioWorkletNode(context, "repoviva-forward");
  source.connect(analyser);
  source.connect(node);

  const downsampler = new Downsampler(context.sampleRate, MIC_RATE);
  let pending: Float32Array[] = [];
  let pendingLength = 0;
  let sink: ((pcm: ArrayBuffer) => void) | null = null;

  const flush = () => {
    if (!sink || pendingLength === 0) return;
    const joined = new Float32Array(pendingLength);
    let offset = 0;
    for (const part of pending) {
      joined.set(part, offset);
      offset += part.length;
    }
    pending = [];
    pendingLength = 0;
    sink(floatToPcm16(joined));
  };

  node.port.onmessage = (event: MessageEvent<Float32Array>) => {
    if (!sink) return;
    const out = downsampler.push(event.data);
    pending.push(out);
    pendingLength += out.length;
    if (pendingLength >= CHUNK_SAMPLES) flush();
  };

  return {
    level() {
      analyser.getFloatTimeDomainData(levelSamples);
      let sum = 0;
      for (const s of levelSamples) sum += s * s;
      return Math.min(1, Math.sqrt(sum / levelSamples.length) * 6);
    },
    record(onChunk) {
      pending = [];
      pendingLength = 0;
      sink = onChunk;
      void context.resume();
    },
    pause() {
      flush();
      sink = null;
    },
    close() {
      sink = null;
      node.port.onmessage = null;
      stream.getTracks().forEach((t) => t.stop());
      void context.close();
    },
  };
}

/** Browser microphone and speaker access, kept behind small functions so
 * pages can be tested without real audio hardware. */

export type MicErrorKind = "denied" | "not-found" | "busy" | "unsupported";

export class MicError extends Error {
  readonly kind: MicErrorKind;

  constructor(kind: MicErrorKind) {
    super(kind);
    this.name = "MicError";
    this.kind = kind;
  }
}

export interface MicSession {
  /** Current input level, 0 (silence) to 1 (very loud). */
  level(): number;
  /** The device actually opened, for the picker. */
  deviceId: string;
  stop(): void;
}

export function micSupported(): boolean {
  return typeof navigator !== "undefined" && Boolean(navigator.mediaDevices?.getUserMedia);
}

/** Open a microphone for level metering. Throws MicError. */
export async function openMicrophone(deviceId?: string): Promise<MicSession> {
  if (!micSupported()) throw new MicError("unsupported");

  let stream: MediaStream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({
      audio: {
        deviceId: deviceId ? { exact: deviceId } : undefined,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
  } catch (error) {
    throw new MicError(errorKind(error));
  }

  const context = new AudioContext();
  const source = context.createMediaStreamSource(stream);
  const analyser = context.createAnalyser();
  analyser.fftSize = 1024;
  source.connect(analyser);
  const samples = new Float32Array(analyser.fftSize);

  return {
    deviceId: stream.getAudioTracks()[0]?.getSettings().deviceId ?? deviceId ?? "",
    level() {
      analyser.getFloatTimeDomainData(samples);
      let sum = 0;
      for (const s of samples) sum += s * s;
      // RMS of speech sits around 0.02–0.2; scale so normal speech fills most of the meter.
      return Math.min(1, Math.sqrt(sum / samples.length) * 6);
    },
    stop() {
      stream.getTracks().forEach((track) => track.stop());
      void context.close();
    },
  };
}

export async function listMicrophones(): Promise<MediaDeviceInfo[]> {
  if (!navigator.mediaDevices?.enumerateDevices) return [];
  const devices = await navigator.mediaDevices.enumerateDevices();
  return devices.filter((d) => d.kind === "audioinput" && d.deviceId !== "");
}

/** A short, soft two-note chime through the default output. */
export async function playTestSound(): Promise<void> {
  const context = new AudioContext();
  const now = context.currentTime;
  [523.25, 659.25].forEach((frequency, i) => {
    const osc = context.createOscillator();
    const gain = context.createGain();
    osc.type = "sine";
    osc.frequency.value = frequency;
    const start = now + i * 0.18;
    gain.gain.setValueAtTime(0, start);
    gain.gain.linearRampToValueAtTime(0.18, start + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, start + 0.5);
    osc.connect(gain).connect(context.destination);
    osc.start(start);
    osc.stop(start + 0.55);
  });
  await new Promise((resolve) => setTimeout(resolve, 800));
  await context.close();
}

function errorKind(error: unknown): MicErrorKind {
  const name = error instanceof DOMException ? error.name : "";
  if (name === "NotAllowedError" || name === "SecurityError") return "denied";
  if (name === "NotFoundError" || name === "OverconstrainedError") return "not-found";
  if (name === "NotReadableError" || name === "AbortError") return "busy";
  return "unsupported";
}

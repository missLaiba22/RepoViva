import { useCallback, useEffect, useRef, useState } from "react";
import { MicError, listMicrophones, openMicrophone, type MicErrorKind, type MicSession } from "./audio/microphone";

export type MicCheck =
  | { state: "idle" }
  | { state: "requesting" }
  | { state: "error"; kind: MicErrorKind }
  | { state: "live"; level: number; heard: boolean; deviceId: string; devices: MediaDeviceInfo[] };

/** Speech has to stay above this level for HEARD_MS to count as "we can hear you". */
const SPEECH_LEVEL = 0.12;
const HEARD_MS = 300;

/** Open the microphone on request, meter it, and notice when the user speaks.
 * The microphone is released on `stop()` and on unmount. */
export function useMicCheck() {
  const [check, setCheck] = useState<MicCheck>({ state: "idle" });
  const session = useRef<MicSession | null>(null);
  const frame = useRef<number | null>(null);

  const release = useCallback(() => {
    if (frame.current !== null) cancelAnimationFrame(frame.current);
    frame.current = null;
    session.current?.stop();
    session.current = null;
  }, []);

  const start = useCallback(
    async (deviceId?: string) => {
      release();
      setCheck({ state: "requesting" });
      let mic: MicSession;
      try {
        mic = await openMicrophone(deviceId);
      } catch (error) {
        setCheck({ state: "error", kind: error instanceof MicError ? error.kind : "unsupported" });
        return;
      }
      session.current = mic;
      // Device labels are only visible once permission is granted.
      const devices = await listMicrophones().catch(() => []);

      let loudSince: number | null = null;
      let heard = false;
      const tick = (now: number) => {
        if (session.current !== mic) return;
        const level = mic.level();
        if (level >= SPEECH_LEVEL) {
          loudSince ??= now;
          if (now - loudSince >= HEARD_MS) heard = true;
        } else {
          loudSince = null;
        }
        setCheck({ state: "live", level, heard, deviceId: mic.deviceId, devices });
        frame.current = requestAnimationFrame(tick);
      };
      frame.current = requestAnimationFrame(tick);
    },
    [release],
  );

  const stop = useCallback(() => {
    release();
    setCheck({ state: "idle" });
  }, [release]);

  useEffect(() => release, [release]);

  return { check, start, stop };
}

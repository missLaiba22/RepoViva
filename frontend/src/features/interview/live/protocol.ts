/** Voice Service WebSocket protocol v2 (voice-service/src/voice_service/session/protocol.py). */

export type ClientMessage =
  | { type: "session.start"; token: string }
  | { type: "audio.end" }
  | { type: "answer.text"; text: string }
  | { type: "session.end" };

export type ServerMessage =
  | { type: "session.ready"; interview_id: number }
  | { type: "question.text"; turn_id: number; seq: number; text: string }
  | { type: "question.audio_end"; turn_id: number }
  | { type: "transcript.final"; turn_id: number; text: string }
  | { type: "turn.complete"; turn_id: number }
  | { type: "session.end"; reason: "completed" | "ended_by_client" }
  | { type: "error"; code: string; message: string };

/** Close codes (architecture.md, WebSocket section). */
export const CLOSE_NORMAL = 1000;
/** Missing, invalid, expired or already-used token. One generic reason (decision 035). */
export const CLOSE_REJECTED = 1008;
export const CLOSE_INTERNAL = 1011;

/** Voice Service's MAX_QUESTIONS default (decision 041). The server doesn't send it. */
export const QUESTIONS_PER_INTERVIEW = 6;
/** The server's limit is 180 s; stop a little early so it never has to refuse. */
export const MAX_ANSWER_SECONDS = 175;
export const MAX_TEXT_ANSWER = 5000;

export function parseServerMessage(raw: string): ServerMessage | null {
  try {
    const msg = JSON.parse(raw);
    return typeof msg?.type === "string" ? (msg as ServerMessage) : null;
  } catch {
    return null;
  }
}

export function voiceSocketUrl(): string {
  // Same origin: Vite proxies /v1/ws to Voice Service in development.
  const scheme = window.location.protocol === "https:" ? "wss" : "ws";
  return `${scheme}://${window.location.host}/v1/ws/interview`;
}

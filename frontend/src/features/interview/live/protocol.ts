/** Voice Service WebSocket protocol v2 (voice-service/src/voice_service/session/protocol.py). */

export type ClientMessage =
  | { type: "session.start"; token: string }
  | { type: "audio.end" }
  | { type: "answer.text"; text: string }
  | { type: "session.end" };

export type ServerMessage =
  /** question_count: the plan's length (decision 062); absent from an older Voice Service. */
  | { type: "session.ready"; interview_id: number; question_count?: number }
  | { type: "question.text"; turn_id: number; seq: number; text: string }
  | { type: "question.audio_end"; turn_id: number }
  | { type: "transcript.final"; turn_id: number; text: string }
  | { type: "turn.complete"; turn_id: number }
  | { type: "session.end"; reason: "completed" | "ended_by_client" }
  | { type: "error"; code: string; message: string };

/** Close code for a missing, invalid, expired or already-used token. One
 * generic reason (decision 035; architecture.md, WebSocket section). */
export const CLOSE_REJECTED = 1008;

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

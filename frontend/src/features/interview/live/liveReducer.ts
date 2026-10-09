import { CLOSE_REJECTED, type ServerMessage } from "./protocol";

/**
 * One interview, as the page sees it:
 *
 *   connecting ─ready→ preparing ─question.text→ asking ─heard→ answering
 *        ▲                                                       │ record / type
 *        │                     preparing ←turn.complete─ sending ←┘
 *   any ─session.end→ done        any ─close / internal_error→ failed
 */
export type Phase =
  | "connecting" // socket opening, token being checked
  | "preparing" // waiting for the next question (retrieval + LLM)
  | "asking" // question shown, its audio streaming or playing
  | "answering" // the user's turn: mic ready, or typing
  | "recording"
  | "sending" // answer sent, waiting for the transcript and turn.complete
  | "ending" // the user asked to stop
  | "done"
  | "failed";

export type Failure = "rejected" | "lost" | "internal";

export interface LiveState {
  phase: Phase;
  seq: number;
  turnId: number | null;
  question: string | null;
  /** The question's audio has fully arrived (question.audio_end). */
  audioComplete: boolean;
  /** What the server heard for the last answer. */
  transcript: string | null;
  /** A recoverable problem to show next to the mic. */
  notice: string | null;
  answered: number;
  outcome: "completed" | "ended_by_client" | null;
  failure: Failure | null;
}

export type LiveEvent =
  | { type: "server"; message: ServerMessage }
  | { type: "question_heard" }
  | { type: "record_started" }
  | { type: "answer_sent" }
  | { type: "end_requested" }
  | { type: "closed"; code: number };

export const initialLiveState: LiveState = {
  phase: "connecting",
  seq: 0,
  turnId: null,
  question: null,
  audioComplete: false,
  transcript: null,
  notice: null,
  answered: 0,
  outcome: null,
  failure: null,
};

const NOTICES: Record<string, string> = {
  no_speech: "We didn't catch that. Tap the mic and try again.",
  answer_too_long: "That answer ran past 3 minutes and wasn't kept. Please answer again, a little shorter.",
  bad_message: "Something went wrong sending that answer. Please try again.",
};

const FINISHED: Phase[] = ["done", "failed"];

export function liveReducer(state: LiveState, event: LiveEvent): LiveState {
  if (FINISHED.includes(state.phase)) return state;

  switch (event.type) {
    case "server":
      return onServer(state, event.message);

    case "question_heard":
      return state.phase === "asking" ? { ...state, phase: "answering" } : state;

    case "record_started":
      return state.phase === "answering" ? { ...state, phase: "recording", notice: null } : state;

    case "answer_sent":
      return state.phase === "answering" || state.phase === "recording"
        ? { ...state, phase: "sending", notice: null }
        : state;

    case "end_requested":
      return { ...state, phase: "ending", notice: null };

    case "closed":
      if (state.phase === "ending") return { ...state, phase: "done", outcome: "ended_by_client" };
      return {
        ...state,
        phase: "failed",
        failure: state.phase === "connecting" && event.code === CLOSE_REJECTED ? "rejected" : "lost",
      };
  }
}

function onServer(state: LiveState, msg: ServerMessage): LiveState {
  switch (msg.type) {
    case "session.ready":
      return state.phase === "connecting" ? { ...state, phase: "preparing" } : state;

    case "question.text":
      if (state.phase === "ending") return { ...state, seq: msg.seq };
      return {
        ...state,
        phase: "asking",
        seq: msg.seq,
        turnId: msg.turn_id,
        question: msg.text,
        audioComplete: false,
        transcript: null,
        notice: null,
      };

    case "question.audio_end":
      return msg.turn_id === state.turnId ? { ...state, audioComplete: true } : state;

    case "transcript.final":
      return { ...state, transcript: msg.text };

    case "turn.complete":
      return state.phase === "ending"
        ? { ...state, answered: state.answered + 1 }
        : { ...state, phase: "preparing", answered: state.answered + 1 };

    case "session.end":
      return { ...state, phase: "done", outcome: msg.reason };

    case "error":
      if (msg.code === "internal_error") return { ...state, phase: "failed", failure: "internal" };
      if (state.phase === "ending") return state;
      return { ...state, phase: "answering", notice: NOTICES[msg.code] ?? msg.message };
  }
}

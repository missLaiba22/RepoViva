import { CLOSE_REJECTED, type ServerMessage } from "./protocol";

/**
 * One interview, as the page sees it:
 *
 *   connecting ─ready→ preparing ─question.text→ asking ─heard→ answering
 *        ▲                                                       │ record / type
 *        │                     preparing ←turn.complete─ sending ←┘
 *   any ─session.end→ done        any ─close / internal_error→ failed
 */
type Phase =
  | "connecting" // socket opening, token being checked
  | "preparing" // waiting for the next question (retrieval + LLM)
  | "asking" // question shown, its audio streaming or playing
  | "answering" // the user's turn: mic ready, or typing
  | "recording"
  | "sending" // answer sent, waiting for the transcript and turn.complete
  | "ending" // the user asked to stop
  | "done"
  | "failed";

export type Failure = "rejected" | "lost" | "internal" | "time_limit";

export interface LiveState {
  phase: Phase;
  seq: number;
  /** How many questions the interview has; null until session.ready says. */
  total: number | null;
  question: string | null;
  /** The repository area (a path) and topic the question is about. */
  area: string | null;
  topic: string | null;
  /** The question's audio has fully arrived (question.audio_end). */
  audioComplete: boolean;
  /** What the server heard for the last answer. */
  transcript: string | null;
  /** Recording, but the mic is held: no audio is sent. */
  paused: boolean;
  /** Length of the last spoken answer, excluding pauses; null for typed. */
  answerSeconds: number | null;
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
  | { type: "record_paused" }
  | { type: "record_resumed" }
  | { type: "answer_sent"; seconds?: number }
  | { type: "end_requested" }
  | { type: "closed"; code: number };

export const initialLiveState: LiveState = {
  phase: "connecting",
  seq: 0,
  total: null,
  question: null,
  area: null,
  topic: null,
  audioComplete: false,
  transcript: null,
  paused: false,
  answerSeconds: null,
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

const FALLBACK_NOTICE = "Something went wrong with that answer. Please try again.";

const FINISHED: Phase[] = ["done", "failed"];

export function liveReducer(state: LiveState, event: LiveEvent): LiveState {
  if (FINISHED.includes(state.phase)) return state;
  const next = reduce(state, event);
  return next.paused && next.phase !== "recording" ? { ...next, paused: false } : next;
}

function reduce(state: LiveState, event: LiveEvent): LiveState {
  switch (event.type) {
    case "server":
      return onServer(state, event.message);

    case "question_heard":
      return state.phase === "asking" ? { ...state, phase: "answering" } : state;

    case "record_started":
      return state.phase === "answering" ? { ...state, phase: "recording", paused: false, notice: null } : state;

    case "record_paused":
      return state.phase === "recording" ? { ...state, paused: true } : state;

    case "record_resumed":
      return state.phase === "recording" ? { ...state, paused: false } : state;

    case "answer_sent":
      return state.phase === "answering" || state.phase === "recording"
        ? { ...state, phase: "sending", answerSeconds: event.seconds ?? null, notice: null }
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
      return state.phase === "connecting"
        ? { ...state, phase: "preparing", total: msg.question_count ?? null }
        : state;

    case "question.text":
      if (state.phase === "ending") return { ...state, seq: msg.seq };
      return {
        ...state,
        phase: "asking",
        seq: msg.seq,
        question: msg.text,
        area: msg.area ?? null,
        topic: msg.topic ?? null,
        audioComplete: false,
        transcript: null,
        answerSeconds: null,
        notice: null,
      };

    case "question.audio_end":
      return msg.seq === state.seq ? { ...state, audioComplete: true } : state;

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
      if (msg.code === "session_time_limit") return { ...state, phase: "failed", failure: "time_limit" };
      if (state.phase === "ending") return state;
      return { ...state, phase: "answering", notice: NOTICES[msg.code] ?? FALLBACK_NOTICE };
  }
}

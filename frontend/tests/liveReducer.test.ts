import { describe, expect, it } from "vitest";
import { initialLiveState, liveReducer, type LiveEvent, type LiveState } from "../src/features/interview/live/liveReducer";
import type { ServerMessage } from "../src/features/interview/live/protocol";

const server = (message: ServerMessage): LiveEvent => ({ type: "server", message });
const run = (events: LiveEvent[], from: LiveState = initialLiveState) => events.reduce(liveReducer, from);

const asked = (seq = 1): LiveEvent[] => [
  server({ type: "question.text", turn_id: seq * 10, seq, text: `Question ${seq}?` }),
  server({ type: "question.audio_end", turn_id: seq * 10 }),
  { type: "question_heard" },
];

describe("liveReducer", () => {
  it("walks one spoken turn from connecting to the next question", () => {
    let state = run([server({ type: "session.ready", interview_id: 21 })]);
    expect(state.phase).toBe("preparing");

    state = run([server({ type: "question.text", turn_id: 10, seq: 1, text: "Why sort the items?" })], state);
    expect(state).toMatchObject({ phase: "asking", seq: 1, question: "Why sort the items?", audioComplete: false });

    state = run([server({ type: "question.audio_end", turn_id: 10 })], state);
    expect(state).toMatchObject({ phase: "asking", audioComplete: true });

    state = run([{ type: "question_heard" }, { type: "record_started" }], state);
    expect(state.phase).toBe("recording");

    state = run([{ type: "answer_sent" }, server({ type: "transcript.final", turn_id: 10, text: "To avoid deadlocks." })], state);
    expect(state).toMatchObject({ phase: "sending", transcript: "To avoid deadlocks." });

    state = run([server({ type: "turn.complete", turn_id: 10 })], state);
    expect(state).toMatchObject({ phase: "preparing", answered: 1, transcript: "To avoid deadlocks." });
  });

  it("can't record before the question has been heard", () => {
    const state = run([server({ type: "session.ready", interview_id: 1 }), server({ type: "question.text", turn_id: 10, seq: 1, text: "Q" }), { type: "record_started" }]);
    expect(state.phase).toBe("asking");
  });

  it.each(["no_speech", "answer_too_long", "bad_message"])("returns the turn to the user on %s", (code) => {
    const state = run([
      server({ type: "session.ready", interview_id: 1 }),
      ...asked(),
      { type: "record_started" },
      { type: "answer_sent" },
      server({ type: "error", code, message: "x" }),
    ]);
    expect(state.phase).toBe("answering");
    expect(state.notice).toBeTruthy();
  });

  it("finishes on session.end and ignores the close that follows", () => {
    const state = run([
      server({ type: "session.ready", interview_id: 1 }),
      server({ type: "session.end", reason: "completed" }),
      { type: "closed", code: 1000 },
    ]);
    expect(state).toMatchObject({ phase: "done", outcome: "completed", failure: null });
  });

  it("reads a 1008 close during admission as a rejected session", () => {
    expect(run([{ type: "closed", code: 1008 }])).toMatchObject({ phase: "failed", failure: "rejected" });
  });

  it("reads any other unexpected close as a lost connection", () => {
    const state = run([server({ type: "session.ready", interview_id: 1 }), ...asked(), { type: "closed", code: 1006 }]);
    expect(state).toMatchObject({ phase: "failed", failure: "lost" });
  });

  it("fails on internal_error", () => {
    const state = run([server({ type: "session.ready", interview_id: 1 }), server({ type: "error", code: "internal_error", message: "x" })]);
    expect(state).toMatchObject({ phase: "failed", failure: "internal" });
  });

  it("ends by the user's request, even if the server only closes", () => {
    const ending = run([server({ type: "session.ready", interview_id: 1 }), ...asked(), { type: "end_requested" }]);
    expect(ending.phase).toBe("ending");
    // A question generated meanwhile doesn't pull the page back into the interview.
    expect(run([server({ type: "question.text", turn_id: 20, seq: 2, text: "Q2" })], ending).phase).toBe("ending");
    expect(run([{ type: "closed", code: 1000 }], ending)).toMatchObject({ phase: "done", outcome: "ended_by_client" });
    expect(run([server({ type: "session.end", reason: "ended_by_client" })], ending)).toMatchObject({
      phase: "done",
      outcome: "ended_by_client",
    });
  });
});

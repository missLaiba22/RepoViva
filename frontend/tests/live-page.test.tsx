import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { USER, renderApp, stubApi } from "./helpers";

// --- Fakes: the browser's audio and Voice Service's socket -----------------

const audio = vi.hoisted(() => ({ recording: null as ((pcm: ArrayBuffer) => void) | null, closed: 0, opened: 0 }));

vi.mock("../src/features/interview/audio/capture", () => ({
  openCapture: vi.fn(async () => {
    audio.opened++;
    return {
      level: () => 0.4,
      record: (onChunk: (pcm: ArrayBuffer) => void) => {
        audio.recording = onChunk;
        onChunk(new ArrayBuffer(3200)); // 100 ms of 16 kHz PCM16
      },
      pause: () => {
        audio.recording?.(new ArrayBuffer(640)); // the flushed tail
        audio.recording = null;
      },
      close: () => void audio.closed++,
    };
  }),
}));

vi.mock("../src/features/interview/audio/player", () => ({
  QuestionPlayer: class {
    blocked = false;
    fed = 0;
    feed() {
      this.fed++;
    }
    reset() {}
    stop() {}
    close() {}
    async drained() {}
    async replay() {}
    async unblock() {}
  },
}));

class FakeSocket {
  static instances: FakeSocket[] = [];
  static OPEN = 1;
  readyState = 0;
  binaryType = "blob";
  sent: (string | ArrayBuffer)[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((e: { data: unknown }) => void) | null = null;
  onclose: ((e: { code: number }) => void) | null = null;

  constructor(public url: string) {
    FakeSocket.instances.push(this);
  }
  send(data: string | ArrayBuffer) {
    this.sent.push(data);
  }
  close(code = 1000) {
    if (this.readyState === 3) return;
    this.readyState = 3;
    this.onclose?.({ code });
  }
  // Server side
  open() {
    this.readyState = 1;
    this.onopen?.();
  }
  push(message: object | ArrayBuffer) {
    this.onmessage?.({ data: message instanceof ArrayBuffer ? message : JSON.stringify(message) });
  }
  json() {
    return this.sent.filter((d): d is string => typeof d === "string").map((d) => JSON.parse(d));
  }
  binary() {
    return this.sent.filter((d) => d instanceof ArrayBuffer);
  }
}

const HANDOFF = {
  interviewId: 21,
  token: "raw-token-abc",
  tokenExpiresAt: "2026-10-09T10:05:00Z",
  repositoryId: 15,
  repositoryName: "ecommerce-api",
  mode: "voice" as const,
  deviceId: "mic-1",
};

async function startLive(handoff: object = HANDOFF) {
  stubApi({ "GET /v1/me": { body: USER } });
  vi.stubGlobal("WebSocket", FakeSocket);
  const router = renderApp("/");
  await act(() => router.navigate("/interviews/21/live", { state: handoff }));
  await waitFor(() => expect(FakeSocket.instances.length).toBeGreaterThan(0));
  const ws = FakeSocket.instances.at(-1)!;
  act(() => ws.open());
  return { router, ws };
}

async function askQuestion(ws: FakeSocket, seq: number, text: string) {
  act(() => {
    ws.push({ type: "question.text", turn_id: seq * 10, seq, text });
    ws.push(new ArrayBuffer(4800));
    ws.push({ type: "question.audio_end", turn_id: seq * 10 });
  });
  await screen.findByText(text);
}

beforeEach(() => {
  FakeSocket.instances = [];
  audio.recording = null;
  audio.closed = 0;
  audio.opened = 0;
});

describe("live interview", () => {
  it("sends the token as the first message, never in the URL", async () => {
    const { ws } = await startLive();
    expect(ws.url).toMatch(/\/v1\/ws\/interview$/);
    expect(ws.url).not.toContain("raw-token-abc");
    expect(ws.json()[0]).toEqual({ type: "session.start", token: "raw-token-abc" });
  });

  it("runs a spoken answer: record, stream audio, audio.end, transcript, next question", async () => {
    const { ws } = await startLive();
    act(() => ws.push({ type: "session.ready", interview_id: 21 }));
    expect(await screen.findByText(/preparing the first question/i)).toBeInTheDocument();

    await askQuestion(ws, 1, "Why does checkout sort items before locking?");
    expect(screen.getByText("Question 1 of 6")).toBeInTheDocument();
    await waitFor(() => expect(audio.opened).toBe(1));

    await userEvent.click(await screen.findByRole("button", { name: /start answering/i }));
    expect(screen.getByText(/listening/i)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /stop and send/i }));

    expect(ws.binary()).toHaveLength(2); // the first chunk and the flushed tail, before audio.end
    expect(ws.json().at(-1)).toEqual({ type: "audio.end" });
    expect(screen.getByText(/transcribing/i)).toBeInTheDocument();

    act(() => {
      ws.push({ type: "transcript.final", turn_id: 10, text: "So two checkouts never deadlock." });
      ws.push({ type: "turn.complete", turn_id: 10 });
    });
    expect(screen.getByText("So two checkouts never deadlock.")).toBeInTheDocument();
    expect(screen.getByText(/thinking of the next question/i)).toBeInTheDocument();

    await askQuestion(ws, 2, "What happens if the promo is invalid?");
    expect(screen.getByText("Question 2 of 6")).toBeInTheDocument();
  });

  it("lets the user try again after no speech", async () => {
    const { ws } = await startLive();
    act(() => ws.push({ type: "session.ready", interview_id: 21 }));
    await askQuestion(ws, 1, "Q1?");
    await waitFor(() => expect(audio.opened).toBe(1));
    await userEvent.click(await screen.findByRole("button", { name: /start answering/i }));
    await userEvent.click(screen.getByRole("button", { name: /stop and send/i }));

    act(() => ws.push({ type: "error", code: "no_speech", message: "no speech heard" }));
    expect(screen.getByRole("alert")).toHaveTextContent(/didn't catch that/i);
    expect(screen.getByRole("button", { name: /start answering/i })).toBeEnabled();
  });

  it("sends typed answers as answer.text", async () => {
    const { ws } = await startLive({ ...HANDOFF, mode: "text" });
    act(() => ws.push({ type: "session.ready", interview_id: 21 }));
    await askQuestion(ws, 1, "Q1?");

    await userEvent.type(await screen.findByLabelText(/your answer/i), "It sorts by product id.");
    await userEvent.click(screen.getByRole("button", { name: /send answer/i }));

    expect(ws.json().at(-1)).toEqual({ type: "answer.text", text: "It sorts by product id." });
    expect(audio.opened).toBe(0);
  });

  it("shows the finish screen with a link to the report", async () => {
    const { ws } = await startLive();
    act(() => {
      ws.push({ type: "session.ready", interview_id: 21 });
      ws.push({ type: "session.end", reason: "completed" });
      ws.close(1000);
    });
    expect(await screen.findByRole("heading", { name: /interview complete/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /see your report/i })).toHaveAttribute("href", "/interviews/21/report");
  });

  it("ends early with session.end after confirming", async () => {
    const { ws } = await startLive();
    act(() => ws.push({ type: "session.ready", interview_id: 21 }));
    await askQuestion(ws, 1, "Q1?");

    await userEvent.click(screen.getByRole("button", { name: /^end interview$/i }));
    expect(screen.getByText(/end the interview now/i)).toBeInTheDocument();
    await userEvent.click(screen.getAllByRole("button", { name: /^end interview$/i }).at(-1)!);

    expect(ws.json().at(-1)).toEqual({ type: "session.end" });
    act(() => {
      ws.push({ type: "session.end", reason: "ended_by_client" });
      ws.close(1000);
    });
    expect(await screen.findByRole("heading", { name: /interview ended/i })).toBeInTheDocument();
  });

  it("explains an expired or reused session", async () => {
    const { ws } = await startLive();
    act(() => ws.close(1008));
    expect(await screen.findByRole("heading", { name: /session has expired/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /start a new interview/i })).toHaveAttribute(
      "href",
      "/repositories/15/interview",
    );
  });

  it("can't be reopened without the in-memory hand-off", async () => {
    stubApi({ "GET /v1/me": { body: USER } });
    vi.stubGlobal("WebSocket", FakeSocket);
    renderApp("/interviews/21/live");

    expect(await screen.findByRole("heading", { name: /can.t be reopened/i })).toBeInTheDocument();
    expect(FakeSocket.instances).toHaveLength(0);
  });

  it("closes the socket and the microphone when the page goes away", async () => {
    const { router, ws } = await startLive();
    act(() => ws.push({ type: "session.ready", interview_id: 21 }));
    await waitFor(() => expect(audio.opened).toBe(1));
    act(() => ws.push({ type: "session.end", reason: "completed" }));
    await screen.findByRole("heading", { name: /interview complete/i });

    await act(() => router.navigate("/home"));
    expect(ws.readyState).toBe(3);
    expect(audio.closed).toBe(1);
  });
});

import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { USER, renderApp, repository, stubApi } from "./helpers";

const mic = vi.hoisted(() => ({ level: 0, stopped: 0, fail: null as string | null }));

vi.mock("../src/features/interview/audio/microphone", async (original) => {
  const real = await original<typeof import("../src/features/interview/audio/microphone")>();
  return {
    ...real,
    micSupported: () => true,
    openMicrophone: vi.fn(async () => {
      if (mic.fail) throw new real.MicError(mic.fail as never);
      return { deviceId: "mic-1", level: () => mic.level, stop: () => void mic.stopped++ };
    }),
    listMicrophones: vi.fn(async () => [
      { deviceId: "mic-1", kind: "audioinput", label: "Laptop microphone" },
      { deviceId: "mic-2", kind: "audioinput", label: "Headset" },
    ]),
    playTestSound: vi.fn(async () => {}),
  };
});

const CREATED = {
  id: 21,
  repository_id: 15,
  status: "created",
  error_message: null,
  started_at: null,
  ended_at: null,
  created_at: "2026-10-09T10:00:00Z",
  updated_at: "2026-10-09T10:00:00Z",
  session_token: "raw-token-abc",
  session_token_expires_at: "2026-10-09T10:05:00Z",
};

function readyRepo() {
  return stubApi({
    "GET /v1/me": { body: USER },
    "GET /v1/repositories/15": { body: repository() },
    "POST /v1/interviews": { status: 201, body: CREATED },
  });
}

beforeEach(() => {
  mic.level = 0;
  mic.stopped = 0;
  mic.fail = null;
});

describe("interview setup", () => {
  it("only enables Start once the microphone has heard speech", async () => {
    readyRepo();
    renderApp("/repositories/15/interview");

    const start = await screen.findByRole("button", { name: /start interview/i });
    expect(start).toBeDisabled();

    await userEvent.click(screen.getByRole("button", { name: /check my microphone/i }));
    expect(await screen.findByRole("meter", { name: /microphone level/i })).toBeInTheDocument();
    expect(start).toBeDisabled();

    mic.level = 0.5;
    expect(await screen.findByText(/we can hear you/i)).toBeInTheDocument();
    expect(start).toBeEnabled();
  });

  it("offers a microphone picker when there is more than one", async () => {
    readyRepo();
    renderApp("/repositories/15/interview");
    await userEvent.click(await screen.findByRole("button", { name: /check my microphone/i }));

    const picker = await screen.findByLabelText("Input");
    expect(picker).toHaveValue("mic-1");
    expect(screen.getByRole("option", { name: "Headset" })).toBeInTheDocument();
  });

  it("explains a blocked microphone and offers to type instead", async () => {
    readyRepo();
    mic.fail = "denied";
    renderApp("/repositories/15/interview");
    await userEvent.click(await screen.findByRole("button", { name: /check my microphone/i }));

    expect(await screen.findByText(/microphone access is blocked/i)).toBeInTheDocument();
    await userEvent.click(screen.getByLabelText(/type my answers/i));
    expect(screen.getByRole("button", { name: /start interview/i })).toBeEnabled();
  });

  it("creates the interview only on Start, and hands the token over in memory", async () => {
    const api = readyRepo();
    const router = renderApp("/repositories/15/interview");
    await userEvent.click(await screen.findByRole("button", { name: /check my microphone/i }));
    mic.level = 0.5;
    await screen.findByText(/we can hear you/i);
    expect(api.calls).not.toContain("POST /v1/interviews");

    await userEvent.click(screen.getByRole("button", { name: /start interview/i }));

    await waitFor(() => expect(router.state.location.pathname).toBe("/interviews/21/live"));
    expect(router.state.location.state).toMatchObject({
      interviewId: 21,
      token: "raw-token-abc",
      mode: "voice",
      deviceId: "mic-1",
    });
    expect(router.state.location.search).toBe("");
    expect(mic.stopped).toBeGreaterThan(0);
  });

  it("starts a typed interview without touching the microphone", async () => {
    readyRepo();
    const router = renderApp("/repositories/15/interview");
    await userEvent.click(await screen.findByLabelText(/type my answers/i));
    await userEvent.click(screen.getByRole("button", { name: /start interview/i }));

    await waitFor(() => expect(router.state.location.pathname).toBe("/interviews/21/live"));
    expect(router.state.location.state).toMatchObject({ mode: "text" });
  });

  it("shows a message and stays put if the interview can't be created", async () => {
    stubApi({
      "GET /v1/me": { body: USER },
      "GET /v1/repositories/15": { body: repository() },
      "POST /v1/interviews": { status: 409, body: { detail: "Repository is 'failed'" } },
    });
    const router = renderApp("/repositories/15/interview");
    await userEvent.click(await screen.findByLabelText(/type my answers/i));
    await userEvent.click(screen.getByRole("button", { name: /start interview/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/no longer ready/i);
    expect(router.state.location.pathname).toBe("/repositories/15/interview");
  });

  it("sends a repository that isn't ready back to its status", async () => {
    stubApi({
      "GET /v1/me": { body: USER },
      "GET /v1/repositories/15": { body: repository({ status: "in_progress" }) },
    });
    renderApp("/repositories/15/interview");

    expect(await screen.findByRole("heading", { name: /isn't ready yet/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /see its status/i })).toHaveAttribute("href", "/repositories/15");
  });
});

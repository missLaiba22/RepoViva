import { act, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { USER, interview, renderApp, repository, stubApi } from "./helpers";

const source = (chunk_id: number, filename: string, start_line: number, end_line: number) => ({
  chunk_id,
  filename,
  start_line,
  end_line,
});

const READY = {
  interview_id: 10,
  status: "ready",
  partial: false,
  model: "groq/openai/gpt-oss-120b",
  prompt_version: "v5",
  created_at: "2026-10-08T10:15:00Z",
  completed_at: "2026-10-08T10:16:16Z",
  summary: {
    average_correctness: 2.5,
    average_clarity: 2.7,
    turns_asked: 2,
    turns_answered: 1,
    turns_graded: 1,
    strengths: ["Named the canonical lock order."],
    improvements: ["Explain what happens to reserved stock when a session expires."],
    files_to_revisit: [{ file: "backend/app/modules/orders/service.py", reason: "Study how stock is released." }],
  },
  turn_evaluations: [
    {
      seq: 1,
      status: "graded",
      question: "Why does checkout sort items before locking?",
      answer: "So two checkouts lock rows in the same order.",
      correctness: { score: 4, justification: "Matches the sort in service.py." },
      clarity: { score: 3, justification: "Clear but brief." },
      strengths: ["Identified the sort."],
      gaps: ["Didn't mention promo locking."],
      key_points: [
        {
          point: "Items are sorted by product_id before SELECT … FOR UPDATE.",
          sources: [source(142, "backend/app/modules/orders/service.py", 12, 40)],
        },
      ],
      evidence: [source(142, "backend/app/modules/orders/service.py", 12, 40)],
      sources: [source(142, "backend/app/modules/orders/service.py", 12, 40), source(244, "backend/app/modules/promotions/service.py", 50, 60)],
    },
    { seq: 2, status: "not_answered", answer: null, question: "What happens to an abandoned checkout?" },
  ],
};

function api(report: object | null, overrides: Record<string, { status?: number; body?: unknown }> = {}) {
  return stubApi({
    "GET /v1/me": { body: USER },
    "GET /v1/interviews/10": { body: interview() },
    "GET /v1/repositories/15": { body: repository() },
    ...(report ? { "GET /v1/interviews/10/report": { body: report } } : {}),
    ...overrides,
  });
}

describe("report", () => {
  it("leads with the scores and the three takeaways", async () => {
    api(READY);
    renderApp("/interviews/10/report");

    expect(await screen.findByText("2.5")).toBeInTheDocument();
    expect(screen.getByText("2.7")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "What went well" })).toBeInTheDocument();
    expect(screen.getByText("Named the canonical lock order.")).toBeInTheDocument();
    expect(screen.getByText(/reserved stock when a session expires/)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "backend/app/modules/orders/service.py" })).toHaveAttribute(
      "href",
      "https://github.com/missLaiba22/ecommerce-api/blob/HEAD/backend/app/modules/orders/service.py",
    );
  });

  it("shows each question with its feedback, key points and sources", async () => {
    api(READY);
    renderApp("/interviews/10/report");

    const list = await screen.findByRole("list", { name: "Questions" });
    const [graded, unanswered] = within(list).getAllByRole("listitem").filter((li) => li.parentElement === list);

    await userEvent.click(within(graded).getByText(/why does checkout sort/i));
    expect(within(graded).getByText("So two checkouts lock rows in the same order.")).toBeVisible();
    expect(within(graded).getByText("Matches the sort in service.py.")).toBeInTheDocument();
    expect(within(graded).getByText(/sorted by product_id/)).toBeInTheDocument();

    const chips = within(graded).getAllByRole("link", { name: /service\.py:12–40/ });
    expect(chips[0]).toHaveAttribute(
      "href",
      "https://github.com/missLaiba22/ecommerce-api/blob/HEAD/backend/app/modules/orders/service.py#L12-L40",
    );

    expect(within(unanswered).getByText(/not answered/i)).toBeInTheDocument();
  });

  it("waits while grading, then shows the report", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const stub = api({ interview_id: 10, status: "generating" });
    renderApp("/interviews/10/report");
    expect(await screen.findByRole("heading", { name: /grading your answers/i })).toBeInTheDocument();

    stub.fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const path = String(input);
      const body =
        path === "/v1/interviews/10/report" ? READY : path === "/v1/me" ? USER : path === "/v1/interviews/10" ? interview() : repository();
      return new Response(JSON.stringify(body), { status: 200 });
    });
    await act(() => vi.advanceTimersByTimeAsync(4100));

    expect(await screen.findByText("2.5")).toBeInTheDocument();
  });

  it("lets a failed report be graded again", async () => {
    const stub = api(
      { interview_id: 10, status: "failed" },
      { "POST /v1/interviews/10/report/retry": { status: 202, body: { interview_id: 10, status: "generating" } } },
    );
    renderApp("/interviews/10/report");

    await userEvent.click(await screen.findByRole("button", { name: /try grading again/i }));

    expect(stub.calls).toContain("POST /v1/interviews/10/report/retry");
    expect(await screen.findByRole("heading", { name: /grading your answers/i })).toBeInTheDocument();
  });

  it("says when there are no scores because nothing was graded", async () => {
    api({
      ...READY,
      summary: { ...READY.summary, average_correctness: null, average_clarity: null, turns_graded: 0, turns_answered: 0, strengths: [], improvements: [], files_to_revisit: [] },
      turn_evaluations: [READY.turn_evaluations[1]],
    });
    renderApp("/interviews/10/report");

    expect(await screen.findByText(/no answers were graded/i)).toBeInTheDocument();
    expect(screen.getAllByText("–")).toHaveLength(2);
  });

  it("doesn't ask for a report before the interview has ended", async () => {
    const stub = api(null, { "GET /v1/interviews/10": { body: interview({ status: "active", ended_at: null }) } });
    renderApp("/interviews/10/report");

    expect(await screen.findByRole("heading", { name: /hasn't finished/i })).toBeInTheDocument();
    expect(stub.calls.some((c) => c.endsWith("/report"))).toBe(false);
  });

  it("says not found for someone else's interview", async () => {
    stubApi({ "GET /v1/me": { body: USER } });
    renderApp("/interviews/99/report");

    expect(await screen.findByRole("heading", { name: /report not found/i })).toBeInTheDocument();
  });

  it("marks an interview that ended early", async () => {
    api(READY, { "GET /v1/interviews/10": { body: interview({ status: "interrupted" }) } });
    renderApp("/interviews/10/report");

    expect(await screen.findByText("Ended early")).toBeInTheDocument();
  });
});

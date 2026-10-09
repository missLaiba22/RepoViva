import { act, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { USER, interview, renderApp, repository, stubApi } from "./helpers";

function signedIn(repositories: unknown[], interviews: unknown[] = []) {
  return stubApi({
    "GET /v1/me": { body: USER },
    "GET /v1/repositories": { body: repositories },
    "GET /v1/interviews": { body: interviews },
  });
}

describe("home", () => {
  it("shows a first-visit empty state with one way forward", async () => {
    signedIn([]);
    renderApp("/home");

    expect(await screen.findByRole("heading", { name: /connect your first repository/i })).toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: /connect repository/i })).toHaveLength(1);
    expect(screen.getByText(/no interviews yet/i)).toBeInTheDocument();
  });

  it("lists repositories with status, and offers an interview only when ready", async () => {
    signedIn([
      repository(),
      repository({ id: 16, github_url: "https://github.com/missLaiba22/repoviva", status: "in_progress" }),
      repository({ id: 17, github_url: "https://github.com/a/broken", status: "failed", error_message: "Clone failed" }),
    ]);
    renderApp("/home");

    const list = await screen.findByRole("list", { name: "Repositories" });
    const rows = within(list).getAllByRole("listitem");
    expect(rows).toHaveLength(3);
    expect(within(rows[0]).getByText("Ready")).toBeInTheDocument();
    expect(within(rows[0]).getByRole("link", { name: /start interview/i })).toHaveAttribute(
      "href",
      "/repositories/15/interview",
    );
    expect(within(rows[1]).getByText("Indexing")).toBeInTheDocument();
    expect(within(rows[1]).queryByRole("link", { name: /start interview/i })).toBeNull();
    expect(within(rows[2]).getByText("Clone failed")).toBeInTheDocument();
  });

  it("lists interviews with a report link only once they have ended", async () => {
    signedIn(
      [repository()],
      [interview(), interview({ id: 11, status: "interrupted" }), interview({ id: 12, status: "active", ended_at: null })],
    );
    renderApp("/home");

    const section = (await screen.findByRole("heading", { name: /recent interviews/i })).closest("section")!;
    const rows = within(section).getAllByRole("listitem");
    expect(within(rows[0]).getByText("Completed")).toBeInTheDocument();
    expect(within(rows[0]).getByText(/14 min/)).toBeInTheDocument();
    expect(within(rows[0]).getByRole("link", { name: /view report/i })).toHaveAttribute("href", "/interviews/10/report");
    expect(within(rows[1]).getByText("Ended early")).toBeInTheDocument();
    expect(within(rows[2]).queryByRole("link", { name: /view report/i })).toBeNull();
  });

  it("hides interviews that never started", async () => {
    signedIn([repository()], [interview(), interview({ id: 13, status: "created", started_at: null, ended_at: null })]);
    renderApp("/home");

    const list = await screen.findByRole("list", { name: "Recent interviews" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(1);
  });

  it("never reads reports from the home page", async () => {
    const api = signedIn([repository()], [interview()]);
    renderApp("/home");
    await screen.findByText("Completed");

    expect(api.calls.some((c) => c.includes("/report"))).toBe(false);
  });

  it("polls while a repository is indexing, and stops once it's ready", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const api = signedIn([repository({ status: "in_progress" })]);
    renderApp("/home");
    await screen.findByText("Indexing");

    api.fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const path = String(input);
      api.calls.push(`GET ${path}`);
      const body = path === "/v1/repositories" ? [repository()] : path === "/v1/me" ? USER : [];
      return new Response(JSON.stringify(body), { status: 200 });
    });
    await act(() => vi.advanceTimersByTimeAsync(3100));
    expect(await screen.findByText("Ready")).toBeInTheDocument();

    const before = api.calls.length;
    await act(() => vi.advanceTimersByTimeAsync(10000));
    expect(api.calls.length).toBe(before);
  });
});

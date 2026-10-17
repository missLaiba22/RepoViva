import { act, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { USER, interview, renderApp, repository, stubApi } from "./helpers";

function signedIn(repositories: unknown[], interviews: unknown[] = []) {
  return stubApi({
    "GET /v1/me": { body: USER },
    "GET /v1/repositories": { body: repositories },
    "GET /v1/interviews": { body: interviews },
  });
}

describe("repositories page", () => {
  it("shows a first-visit empty state with one way forward", async () => {
    signedIn([]);
    renderApp("/repositories");

    expect(await screen.findByRole("heading", { name: /connect your first repository/i })).toBeInTheDocument();
    expect(within(screen.getByRole("main")).getAllByRole("link", { name: /connect repository/i })).toHaveLength(1);
  });

  it("lists repositories with status, and offers an interview only when ready", async () => {
    signedIn([
      repository(),
      repository({ id: 16, github_url: "https://github.com/missLaiba22/repoviva", status: "in_progress" }),
      repository({ id: 17, github_url: "https://github.com/a/broken", status: "failed", error_message: "fetch failed: git clone exited 128" }),
    ]);
    renderApp("/repositories");

    const list = await screen.findByRole("list", { name: "Repositories" });
    const rows = within(list).getAllByRole("listitem");
    expect(rows).toHaveLength(3);
    expect(within(rows[0]).getByText("Ready to practice")).toBeInTheDocument();
    expect(within(rows[0]).getByRole("link", { name: /start interview/i })).toHaveAttribute(
      "href",
      "/repositories/15/interview",
    );
    expect(within(rows[1]).getByText("Preparing")).toBeInTheDocument();
    expect(within(rows[1]).queryByRole("link", { name: /start interview/i })).toBeNull();
    expect(within(rows[2]).getByText("Import failed")).toBeInTheDocument();
    expect(within(rows[2]).getByText("Couldn't prepare this repository.")).toBeInTheDocument();
    expect(within(rows[2]).getByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(within(rows[2]).queryByText(/git clone/)).toBeNull();

    await userEvent.click(within(rows[2]).getByRole("button", { name: "Details" }));
    expect(within(rows[2]).getByText(/git clone exited 128/)).toBeInTheDocument();
  });

  it("lists repositories in the sidebar, and refreshes them after a retry", async () => {
    const failed = repository({ id: 17, github_url: "https://github.com/a/broken", status: "failed", error_message: "fetch failed: x" });
    const api = stubApi({
      "GET /v1/me": { body: USER },
      "GET /v1/repositories": { body: [repository(), failed] },
      "GET /v1/interviews": { body: [] },
      "POST /v1/repositories/17/retry": { status: 202, body: { ...failed, status: "queued" } },
    });
    renderApp("/repositories");

    const sidebar = await screen.findByRole("list", { name: "Your repositories" });
    expect(within(sidebar).getByRole("link", { name: /broken.*import failed/ })).toHaveAttribute("href", "/repositories/17");

    const before = api.calls.filter((c) => c === "GET /v1/repositories").length;
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    await waitFor(() =>
      expect(api.calls.filter((c) => c === "GET /v1/repositories").length).toBeGreaterThanOrEqual(before + 2),
    );
  });

  it("counts each repository's interviews", async () => {
    signedIn([repository()], [interview(), interview({ id: 11, status: "interrupted" })]);
    renderApp("/repositories");

    expect(await screen.findByText(/2 interviews/)).toBeInTheDocument();
  });

  it("opens from /home, where sign-in lands", async () => {
    signedIn([]);
    const router = renderApp("/home");

    await screen.findByRole("heading", { name: "Repositories" });
    expect(router.state.location.pathname).toBe("/repositories");
  });

  it("polls while a repository is indexing, and stops once it's ready", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const api = signedIn([repository({ status: "in_progress" })]);
    renderApp("/repositories");
    await screen.findByText("Preparing");

    api.fetchMock.mockImplementation(async (input: RequestInfo | URL) => {
      const path = String(input);
      api.calls.push(`GET ${path}`);
      const body = path === "/v1/repositories" ? [repository()] : path === "/v1/me" ? USER : [];
      return new Response(JSON.stringify(body), { status: 200 });
    });
    await act(() => vi.advanceTimersByTimeAsync(3100));
    expect(await screen.findByText("Ready to practice")).toBeInTheDocument();

    const before = api.calls.length;
    await act(() => vi.advanceTimersByTimeAsync(10000));
    expect(api.calls.length).toBe(before);
  });
});

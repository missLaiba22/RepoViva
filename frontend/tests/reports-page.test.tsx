import { screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { USER, interview, renderApp, repository, stubApi } from "./helpers";

function signedIn(repositories: unknown[], interviews: unknown[] = []) {
  return stubApi({
    "GET /v1/me": { body: USER },
    "GET /v1/repositories": { body: repositories },
    "GET /v1/interviews": { body: interviews },
  });
}

describe("reports page", () => {
  it("shows an empty state that leads to the repositories", async () => {
    signedIn([repository()]);
    renderApp("/interviews");

    expect(await screen.findByRole("heading", { name: /no reports yet/i })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /choose a repository/i })).toHaveAttribute("href", "/repositories");
  });

  it("lists interviews with a report link only once they have ended", async () => {
    signedIn(
      [repository()],
      [interview(), interview({ id: 11, status: "interrupted" }), interview({ id: 12, status: "active", ended_at: null })],
    );
    renderApp("/interviews");

    const list = await screen.findByRole("list", { name: "Reports" });
    const rows = within(list).getAllByRole("listitem");
    expect(within(rows[0]).getByText("Completed")).toBeInTheDocument();
    expect(within(rows[0]).getByText(/14 min/)).toBeInTheDocument();
    expect(within(rows[0]).getByRole("link", { name: /report/i })).toHaveAttribute("href", "/interviews/10/report");
    expect(within(rows[1]).getByText("Ended early")).toBeInTheDocument();
    expect(within(rows[2]).queryByRole("link")).toBeNull();
  });

  it("narrows to one repository from ?repository=", async () => {
    signedIn(
      [repository(), repository({ id: 16, github_url: "https://github.com/a/other" })],
      [interview(), interview({ id: 11, repository_id: 16 })],
    );
    renderApp("/interviews?repository=16");

    const list = await screen.findByRole("list", { name: "Reports" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(1);
    expect(within(list).getByRole("link")).toHaveAttribute("href", "/interviews/11/report");
    expect(screen.getByRole("link", { name: "other" })).toHaveAttribute("aria-current", "page");
  });

  it("hides interviews that never started", async () => {
    signedIn([repository()], [interview(), interview({ id: 13, status: "created", started_at: null, ended_at: null })]);
    renderApp("/interviews");

    const list = await screen.findByRole("list", { name: "Reports" });
    expect(within(list).getAllByRole("listitem")).toHaveLength(1);
  });

  it("never reads reports, which would start grading", async () => {
    const api = signedIn([repository()], [interview()]);
    renderApp("/interviews");
    await screen.findByText("Completed");

    expect(api.calls.some((c) => c.includes("/report"))).toBe(false);
  });
});

import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { USER, renderApp, stubApi } from "./helpers";

describe("sign-in", () => {
  it("shows the landing page with a GitHub sign-in link when signed out", async () => {
    stubApi({ "GET /v1/me": { status: 401, body: { detail: "Not logged in" } } });
    renderApp("/");

    const link = await screen.findByRole("link", { name: /sign in with github/i });
    expect(link).toHaveAttribute("href", "/v1/auth/github/login");
  });

  it("sends a signed-out visitor from /home back to the landing page", async () => {
    stubApi({ "GET /v1/me": { status: 401 } });
    const router = renderApp("/home");

    await screen.findByRole("link", { name: /sign in with github/i });
    expect(router.state.location.pathname).toBe("/");
  });

  it("sends a signed-in user from the landing page to /home", async () => {
    stubApi({
      "GET /v1/me": { body: USER },
      "GET /v1/repositories": { body: [] },
      "GET /v1/interviews": { body: [] },
    });
    const router = renderApp("/");

    await screen.findByRole("heading", { name: /welcome back, missLaiba22/i });
    expect(router.state.location.pathname).toBe("/home");
  });

  it("offers a retry when Core API can't be reached", async () => {
    stubApi({ "GET /v1/me": { status: 503 } });
    renderApp("/home");

    expect(await screen.findByRole("button", { name: /try again/i })).toBeInTheDocument();
  });

  it("signs out with a POST and returns to the landing page", async () => {
    const api = stubApi({
      "GET /v1/me": { body: USER },
      "GET /v1/repositories": { body: [] },
      "GET /v1/interviews": { body: [] },
      "POST /v1/auth/github/logout": { status: 204 },
    });
    const router = renderApp("/home");
    await screen.findByRole("heading", { name: /welcome back/i });

    // After logout, /v1/me answers 401.
    api.fetchMock.mockImplementation(async (input: RequestInfo | URL, init?: RequestInit) => {
      api.calls.push(`${init?.method ?? "GET"} ${String(input)}`);
      return String(input) === "/v1/auth/github/logout"
        ? new Response(null, { status: 204 })
        : new Response("{}", { status: 401 });
    });
    await userEvent.click(screen.getByRole("button", { name: /sign out/i }));

    await waitFor(() => expect(router.state.location.pathname).toBe("/"));
    expect(api.calls).toContain("POST /v1/auth/github/logout");
    expect(await screen.findByRole("link", { name: /sign in with github/i })).toBeInTheDocument();
  });
});

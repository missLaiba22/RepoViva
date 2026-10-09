import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { USER, renderApp, repository, stubApi } from "./helpers";

describe("connect repository", () => {
  it("normalises the pasted link and opens the new repository's page", async () => {
    const api = stubApi({
      "GET /v1/me": { body: USER },
      "POST /v1/repositories": { status: 201, body: repository({ id: 20, status: "queued" }) },
      "GET /v1/repositories/20": { body: repository({ id: 20, status: "queued" }) },
    });
    const router = renderApp("/repositories/new");

    await userEvent.type(await screen.findByLabelText(/github repository/i), "missLaiba22/ecommerce-api");
    expect(screen.getByText("https://github.com/missLaiba22/ecommerce-api")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: /connect repository/i }));

    await waitFor(() => expect(router.state.location.pathname).toBe("/repositories/20"));
    const post = api.fetchMock.mock.calls.find(([, init]) => init?.method === "POST")!;
    expect(JSON.parse(post[1]!.body as string)).toEqual({
      github_url: "https://github.com/missLaiba22/ecommerce-api",
    });
    expect(await screen.findByRole("heading", { name: /waiting to start/i })).toBeInTheDocument();
  });

  it("explains an invalid link without calling the API", async () => {
    const api = stubApi({ "GET /v1/me": { body: USER } });
    renderApp("/repositories/new");

    await userEvent.type(await screen.findByLabelText(/github repository/i), "https://gitlab.com/a/b");
    await userEvent.click(screen.getByRole("button", { name: /connect repository/i }));

    expect(screen.getByRole("alert")).toHaveTextContent(/doesn't look like a github repository/i);
    expect(api.calls).not.toContain("POST /v1/repositories");
  });

  it("asks for a link when submitted empty", async () => {
    stubApi({ "GET /v1/me": { body: USER } });
    renderApp("/repositories/new");

    await userEvent.click(await screen.findByRole("button", { name: /connect repository/i }));
    expect(screen.getByRole("alert")).toHaveTextContent(/paste the link/i);
  });

  it("treats an already-connected repository as found, not as an error", async () => {
    const existing = repository({ id: 15 });
    stubApi({
      "GET /v1/me": { body: USER },
      "POST /v1/repositories": {
        status: 409,
        body: { detail: { message: "Repository already registered", repository: existing } },
      },
      "GET /v1/repositories/15": { body: existing },
    });
    const router = renderApp("/repositories/new");

    await userEvent.type(await screen.findByLabelText(/github repository/i), existing.github_url);
    await userEvent.click(screen.getByRole("button", { name: /connect repository/i }));

    await waitFor(() => expect(router.state.location.pathname).toBe("/repositories/15"));
    expect(await screen.findByText(/already connected this repository/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /start interview/i })).toHaveAttribute("href", "/repositories/15/interview");
  });

  it("keeps the form and shows a message when the server fails", async () => {
    stubApi({ "GET /v1/me": { body: USER }, "POST /v1/repositories": { status: 500 } });
    renderApp("/repositories/new");

    await userEvent.type(await screen.findByLabelText(/github repository/i), "a/b");
    await userEvent.click(screen.getByRole("button", { name: /connect repository/i }));

    expect(await screen.findByRole("alert")).toHaveTextContent(/something went wrong/i);
    expect(screen.getByRole("button", { name: /connect repository/i })).toBeEnabled();
  });
});

describe("repository page", () => {
  it("polls while indexing and offers the interview when ready", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const api = stubApi({
      "GET /v1/me": { body: USER },
      "GET /v1/repositories/15": { body: repository({ status: "in_progress" }) },
    });
    renderApp("/repositories/15");
    expect(await screen.findByRole("heading", { name: /indexing your code/i })).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toBeInTheDocument();

    api.fetchMock.mockImplementation(async () => new Response(JSON.stringify(repository()), { status: 200 }));
    await act(() => vi.advanceTimersByTimeAsync(2100));

    expect(await screen.findByRole("heading", { name: /ready for an interview/i })).toBeInTheDocument();
    expect(screen.queryByRole("progressbar")).toBeNull();
  });

  it("shows why indexing failed and a way forward", async () => {
    stubApi({
      "GET /v1/me": { body: USER },
      "GET /v1/repositories/17": { body: repository({ id: 17, status: "failed", error_message: "clone failed: not found" }) },
    });
    renderApp("/repositories/17");

    expect(await screen.findByText("clone failed: not found")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /connect another repository/i })).toBeInTheDocument();
  });

  it("says not found for someone else's or a missing repository", async () => {
    stubApi({ "GET /v1/me": { body: USER } });
    renderApp("/repositories/999");

    expect(await screen.findByRole("heading", { name: /repository not found/i })).toBeInTheDocument();
  });
});

import { render } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { vi } from "vitest";
import { router } from "../src/app/router";
import { AuthProvider } from "../src/features/auth";

type Route = Record<string, { status?: number; body?: unknown }>;

/** Stub fetch with canned Core API responses, keyed by "METHOD /path". */
export function stubApi(routes: Route) {
  const calls: string[] = [];
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const key = `${init?.method ?? "GET"} ${String(input)}`;
    calls.push(key);
    const route = routes[key];
    if (!route) return new Response(JSON.stringify({ detail: "Not Found" }), { status: 404 });
    const status = route.status ?? 200;
    return new Response(status === 204 ? null : JSON.stringify(route.body ?? {}), { status });
  });
  vi.stubGlobal("fetch", fetchMock);
  return { calls, fetchMock };
}

/** The real route table in memory, starting at `path`. */
export function renderApp(path: string) {
  const memory = createMemoryRouter(router.routes, { initialEntries: [path] });
  render(
    <AuthProvider>
      <RouterProvider router={memory} />
    </AuthProvider>,
  );
  return memory;
}

export const USER = { id: 1, github_user_id: 99, github_login: "missLaiba22", created_at: "2026-09-01T10:00:00Z" };

export function repository(overrides: Record<string, unknown> = {}) {
  return {
    id: 15,
    github_url: "https://github.com/missLaiba22/ecommerce-api",
    status: "ready",
    error_message: null,
    created_at: "2026-09-20T10:00:00Z",
    updated_at: "2026-09-20T10:05:00Z",
    ...overrides,
  };
}

export function interview(overrides: Record<string, unknown> = {}) {
  return {
    id: 10,
    repository_id: 15,
    status: "completed",
    error_message: null,
    started_at: "2026-10-08T10:00:00Z",
    ended_at: "2026-10-08T10:14:00Z",
    created_at: "2026-10-08T09:59:00Z",
    updated_at: "2026-10-08T10:14:00Z",
    ...overrides,
  };
}

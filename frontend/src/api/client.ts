/** Fetch wrapper for Core API. Same origin in dev (Vite proxies /v1), and the
 * session is an httpOnly cookie, so there is no token to handle here. */

export class ApiError extends Error {
  readonly status: number;
  /** FastAPI's `detail`, as sent: a string, a validation list or an object. */
  readonly detail: unknown;

  constructor(status: number, message: string, detail?: unknown) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(path, {
      method,
      credentials: "same-origin",
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiError(0, "Can't reach RepoViva. Check your connection and try again.");
  }

  if (!response.ok) {
    let message = response.statusText;
    let detail: unknown;
    try {
      detail = (await response.json())?.detail;
      if (typeof detail === "string") message = detail;
    } catch {
      // Not JSON; keep the status text.
    }
    throw new ApiError(response.status, message, detail);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  get: <T>(path: string) => request<T>("GET", path),
  post: <T>(path: string, body?: unknown) => request<T>("POST", path, body),
};

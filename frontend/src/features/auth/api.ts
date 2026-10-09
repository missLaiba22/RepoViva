import { ApiError, api } from "../../api/client";
import type { User } from "../../api/types";

/** The signed-in user, or null when there is no valid session. */
export async function fetchMe(): Promise<User | null> {
  try {
    return await api.get<User>("/v1/me");
  } catch (error) {
    if (error instanceof ApiError && error.status === 401) return null;
    throw error;
  }
}

export function signOut(): Promise<void> {
  return api.post<void>("/v1/auth/github/logout");
}

/** A full-page navigation, not fetch: Core API redirects to GitHub. */
export const SIGN_IN_URL = "/v1/auth/github/login";

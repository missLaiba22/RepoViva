export const PROBLEM_TITLE = "Couldn't prepare this repository";

/** What to tell the user when a repository couldn't be prepared. The raw
 * `error_message` only appears behind "Details". `retryable` is false when
 * trying again can't help (decision 061). */
export function repositoryProblem(errorMessage: string | null): { reason: string; retryable: boolean } {
  const message = errorMessage?.toLowerCase() ?? "";
  if (message.startsWith("repository too large")) {
    return { reason: "It's too large. Try a smaller project.", retryable: false };
  }
  if (message.startsWith("fetch failed")) {
    return { reason: "We couldn't open it. Check that it's public on GitHub.", retryable: true };
  }
  return { reason: "Something went wrong on our side. Try again in a few minutes.", retryable: true };
}

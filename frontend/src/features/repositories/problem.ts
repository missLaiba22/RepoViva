/** What to tell the user when a repository couldn't be prepared. The raw
 * `error_message` is for logs; it never reaches the page. */
export function repositoryProblem(errorMessage: string | null): { title: string; body: string } {
  const message = errorMessage?.toLowerCase() ?? "";
  if (message.startsWith("repository too large")) {
    return {
      title: "This repository is too large",
      body: "Try a smaller project, or a copy that keeps only the code you want to talk about.",
    };
  }
  if (message.startsWith("fetch failed")) {
    return {
      title: "We couldn't open this repository",
      body: "Check that the link points to a public GitHub repository.",
    };
  }
  return {
    title: "Something went wrong on our side",
    body: "It wasn't caused by your repository. You can connect another one in the meantime.",
  };
}

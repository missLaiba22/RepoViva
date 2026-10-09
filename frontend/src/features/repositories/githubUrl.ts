const NAME = "[A-Za-z0-9._-]+";
const FULL = new RegExp(`^(?:https?://)?(?:www\\.)?github\\.com/(${NAME})/(${NAME})(?:[/#?].*)?$`, "i");
const SHORT = new RegExp(`^(${NAME})/(${NAME})$`);

/** Turn what people paste into the one form Core API accepts,
 * `https://github.com/<owner>/<repo>`, or null if it isn't a repository.
 *
 * Accepts `github.com/owner/repo`, `owner/repo`, `.git` clone URLs and
 * links deeper into a repository (`/tree/main/src`, `/blob/...`). */
export function normalizeGithubUrl(input: string): string | null {
  const value = input.trim();
  const match = value.match(FULL) ?? value.match(SHORT);
  if (!match) return null;
  const owner = match[1];
  const repo = match[2].replace(/\.git$/i, "");
  if (!repo || owner === "." || owner === ".." || repo === "." || repo === "..") return null;
  return `https://github.com/${owner}/${repo}`;
}

import { ApiError, api } from "../../api/client";
import { listInterviews } from "../../api/interviews";
import type { Interview, Repository, RepositoryStatus } from "../../api/types";

const listeners = new Set<() => void>();

/** Called after this app connects or retries a repository, so views that
 * hold their own copy of the list (the sidebar) can refresh. */
export function onRepositoriesChanged(listener: () => void): () => void {
  listeners.add(listener);
  return () => {
    listeners.delete(listener);
  };
}

function changed() {
  listeners.forEach((listener) => listener());
}

export function listRepositories(): Promise<Repository[]> {
  return api.get<Repository[]>("/v1/repositories");
}

export function getRepository(id: number): Promise<Repository> {
  return api.get<Repository>(`/v1/repositories/${id}`);
}

/** Repositories with the user's interviews, for each card's interview count.
 *
 * Reports are deliberately not fetched here: reading a report for an ended
 * interview with none makes Core API trigger one, which costs real grading
 * tokens. */
export async function loadRepositoriesPage(): Promise<{ repositories: Repository[]; interviews: Interview[] }> {
  const [repositories, interviews] = await Promise.all([listRepositories(), listInterviews()]);
  return { repositories, interviews };
}

type ConnectResult =
  | { kind: "created"; repository: Repository }
  | { kind: "existing"; repository: Repository };

/** Register a repository. Connecting one you already have isn't an error
 * for the user: Core API answers 409 with the existing row, returned here. */
export async function connectRepository(githubUrl: string): Promise<ConnectResult> {
  try {
    const repository = await api.post<Repository>("/v1/repositories", { github_url: githubUrl });
    changed();
    return { kind: "created", repository };
  } catch (error) {
    const existing = existingFrom409(error);
    if (existing) return { kind: "existing", repository: existing };
    throw error;
  }
}

function existingFrom409(error: unknown): Repository | null {
  if (!(error instanceof ApiError) || error.status !== 409) return null;
  const detail = error.detail as { repository?: Repository } | undefined;
  return detail?.repository ?? null;
}

/** "Try again" for a failed repository (decision 061): it goes back to
 * `queued`. Any other repository comes back as is. */
export async function retryRepository(id: number): Promise<Repository> {
  const repository = await api.post<Repository>(`/v1/repositories/${id}/retry`);
  changed();
  return repository;
}

/** Still being cloned and indexed: worth polling. */
export function isIndexing(status: RepositoryStatus): boolean {
  return status === "queued" || status === "in_progress";
}

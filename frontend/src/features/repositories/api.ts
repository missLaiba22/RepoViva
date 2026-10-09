import { ApiError, api } from "../../api/client";
import type { Repository, RepositoryStatus } from "../../api/types";

export function listRepositories(): Promise<Repository[]> {
  return api.get<Repository[]>("/v1/repositories");
}

export function getRepository(id: number): Promise<Repository> {
  return api.get<Repository>(`/v1/repositories/${id}`);
}

export type ConnectResult =
  | { kind: "created"; repository: Repository }
  | { kind: "existing"; repository: Repository };

/** Register a repository. Connecting one you already have isn't an error
 * for the user: Core API answers 409 with the existing row, returned here. */
export async function connectRepository(githubUrl: string): Promise<ConnectResult> {
  try {
    const repository = await api.post<Repository>("/v1/repositories", { github_url: githubUrl });
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

/** Still being cloned and indexed: worth polling. */
export function isIndexing(status: RepositoryStatus): boolean {
  return status === "queued" || status === "in_progress";
}

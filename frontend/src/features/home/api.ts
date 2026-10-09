import { api } from "../../api/client";
import type { Interview, Repository } from "../../api/types";
import { listRepositories } from "../repositories";

export interface HomeData {
  repositories: Repository[];
  interviews: Interview[];
}

/** Both lists in parallel. Interviews come back newest first.
 *
 * Reports are deliberately not fetched here: reading a report for an ended
 * interview with none makes Core API trigger one, which costs real grading
 * tokens. Scores live on the report page. */
export async function loadHome(): Promise<HomeData> {
  const [repositories, interviews] = await Promise.all([
    listRepositories(),
    api.get<Interview[]>("/v1/interviews"),
  ]);
  return { repositories, interviews };
}

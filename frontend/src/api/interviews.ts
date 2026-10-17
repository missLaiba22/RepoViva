import { api } from "./client";
import type { Interview } from "./types";

/** The user's interviews, newest first, leaving out ones that never started
 * (the token expired unused, or the tab closed before connecting): not
 * something the user did. */
export async function listInterviews(): Promise<Interview[]> {
  const interviews = await api.get<Interview[]>("/v1/interviews");
  return interviews.filter((i) => i.status !== "created");
}

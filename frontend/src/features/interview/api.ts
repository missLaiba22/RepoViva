import { api } from "../../api/client";
import type { InterviewCreated, Plan } from "../../api/types";

/** Creates the interview and issues its single-use session token, valid
 * for 5 minutes, so call it only when the user presses Start. */
export function createInterview(repositoryId: number): Promise<InterviewCreated> {
  return api.post<InterviewCreated>("/v1/interviews", { repository_id: repositoryId });
}

export function getPlan(interviewId: number): Promise<Plan> {
  return api.get<Plan>(`/v1/interviews/${interviewId}/plan`);
}

export function retryPlan(interviewId: number): Promise<Plan> {
  return api.post<Plan>(`/v1/interviews/${interviewId}/plan/retry`);
}

export type AnswerMode = "voice" | "text";

/** What the setup page hands the live page, through router state only:
 * the token must never reach the URL, history entries' URLs or storage. */
export interface LiveHandoff {
  interviewId: number;
  token: string;
  tokenExpiresAt: string;
  repositoryId: number;
  repositoryName: string;
  mode: AnswerMode;
  deviceId?: string;
}

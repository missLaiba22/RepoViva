import { api } from "../../api/client";
import type { Interview, Report, Repository } from "../../api/types";
import { getRepository } from "../repositories";

export interface ReportContext {
  interview: Interview;
  repository: Repository;
}

/** The interview and its repository: the report's header, and the base for source links. */
export async function loadReportContext(interviewId: number): Promise<ReportContext> {
  const interview = await api.get<Interview>(`/v1/interviews/${interviewId}`);
  const repository = await getRepository(interview.repository_id);
  return { interview, repository };
}

/** 200 (ready or failed) and 202 (generating) both carry the report body. */
export function getReport(interviewId: number): Promise<Report> {
  return api.get<Report>(`/v1/interviews/${interviewId}/report`);
}

export function retryReport(interviewId: number): Promise<Report> {
  return api.post<Report>(`/v1/interviews/${interviewId}/report/retry`);
}

export function hasEnded(interview: Interview): boolean {
  return interview.status === "completed" || interview.status === "interrupted";
}

/** A GitHub link to the lines a source points at, on the default branch.
 * The code may have changed since it was indexed. */
export function sourceUrl(githubUrl: string, source: { filename: string; start_line?: number; end_line?: number }): string {
  const path = source.filename.split("/").map(encodeURIComponent).join("/");
  const lines = source.start_line ? `#L${source.start_line}-L${source.end_line ?? source.start_line}` : "";
  return `${githubUrl}/blob/HEAD/${path}${lines}`;
}

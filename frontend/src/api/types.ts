/** Mirrors Core API's response schemas (the schemas.py in each core_api package). */

export interface User {
  id: number;
  github_user_id: number;
  github_login: string;
  created_at: string;
}

export type RepositoryStatus = "queued" | "in_progress" | "ready" | "failed";

export interface Repository {
  id: number;
  github_url: string;
  status: RepositoryStatus;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export type InterviewStatus = "created" | "active" | "completed" | "interrupted";

export interface Interview {
  id: number;
  repository_id: number;
  status: InterviewStatus;
  error_message: string | null;
  started_at: string | null;
  ended_at: string | null;
  created_at: string;
  updated_at: string;
}

/** POST /v1/interviews only: the one response that carries the raw session
 * token (decision 035). Keep it in memory; never in the URL or storage. */
export interface InterviewCreated extends Interview {
  session_token: string;
  session_token_expires_at: string;
}

/** GET /v1/interviews/{id}/report (decisions 049, 050). Content fields are
 * null while `generating` and when `failed`. */
export interface Report {
  interview_id: number;
  status: "generating" | "ready" | "failed";
  partial: boolean | null;
  model: string | null;
  prompt_version: string | null;
  summary: ReportSummary | null;
  turn_evaluations: TurnEvaluation[] | null;
  created_at: string | null;
  completed_at: string | null;
}

export interface ReportSummary {
  /** Averages over graded turns; null when none were graded. */
  average_correctness: number | null;
  average_clarity: number | null;
  turns_asked: number;
  turns_answered: number;
  turns_graded: number;
  strengths: string[];
  improvements: string[];
  files_to_revisit: { file: string; reason: string }[];
}

/** A pointer into the repository; the code itself stays in Repository Service. */
export interface Source {
  chunk_id: number;
  filename: string;
  start_line: number;
  end_line: number;
}

export interface Score {
  score: number;
  justification: string;
}

export type TurnEvaluation =
  | { seq: number; question: string; answer: null; status: "not_answered" }
  | { seq: number; question: string; answer: string; status: "not_graded"; sources: Source[] }
  | {
      seq: number;
      question: string;
      answer: string;
      status: "graded";
      correctness: Score;
      clarity: Score;
      strengths: string[];
      gaps: string[];
      key_points: { point: string; sources: Source[] }[];
      evidence: Source[];
      sources: Source[];
    };

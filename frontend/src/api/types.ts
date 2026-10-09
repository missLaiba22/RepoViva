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

import type { Interview, Repository } from "../../api/types";
import { ButtonLink } from "../../components/Button";
import { Card } from "../../components/Card";
import { durationMinutes, formatDateTime, repoName } from "../../lib/format";
import styles from "./RecentInterviews.module.css";

const OUTCOME: Record<Interview["status"], { label: string; tone: string }> = {
  completed: { label: "Completed", tone: styles.done },
  interrupted: { label: "Ended early", tone: styles.partial },
  active: { label: "In progress", tone: styles.live },
  created: { label: "Not started", tone: styles.muted },
};

export function RecentInterviews({ interviews, repositories }: { interviews: Interview[]; repositories: Repository[] }) {
  const names = new Map(repositories.map((r) => [r.id, repoName(r.github_url).name]));

  return (
    <Card>
      <ul className={styles.list} aria-label="Recent interviews">
        {interviews.map((interview) => {
          const outcome = OUTCOME[interview.status];
          const ended = interview.status === "completed" || interview.status === "interrupted";
          const minutes = durationMinutes(interview.started_at, interview.ended_at);
          return (
            <li key={interview.id} className={styles.row}>
              <div className={styles.main}>
                <p className={styles.title}>
                  <span className={styles.repo}>{names.get(interview.repository_id) ?? "Repository"}</span>
                  <span className={`${styles.outcome} ${outcome.tone}`}>{outcome.label}</span>
                </p>
                <p className={styles.meta}>
                  {formatDateTime(interview.started_at ?? interview.created_at)}
                  {minutes !== null && ` · ${minutes} min`}
                </p>
              </div>
              {ended && (
                <ButtonLink to={`/interviews/${interview.id}/report`} variant="secondary">
                  View report
                </ButtonLink>
              )}
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

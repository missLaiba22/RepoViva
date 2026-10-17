import type { Interview, Repository } from "../api/types";
import { durationMinutes, formatDateTime, repoName } from "../lib/format";
import { ButtonLink } from "./Button";
import { Card } from "./Card";
import styles from "./InterviewList.module.css";

const OUTCOME: Record<Interview["status"], { label: string; tone: string }> = {
  completed: { label: "Completed", tone: styles.done },
  interrupted: { label: "Ended early", tone: styles.partial },
  active: { label: "In progress", tone: styles.live },
  created: { label: "Not started", tone: styles.muted },
};

/** Past interviews, each with its report once it has ended. With
 * `repositories`, each row names its repository; without, the list is for
 * one repository and leads with the date. */
export function InterviewList({
  interviews,
  repositories,
  label,
}: {
  interviews: Interview[];
  repositories?: Repository[];
  label: string;
}) {
  const names = new Map(repositories?.map((r) => [r.id, repoName(r.github_url).name]));

  return (
    <Card>
      <ul className={styles.list} aria-label={label}>
        {interviews.map((interview) => {
          const outcome = OUTCOME[interview.status];
          const ended = interview.status === "completed" || interview.status === "interrupted";
          const when = formatDateTime(interview.started_at ?? interview.created_at);
          const minutes = durationMinutes(interview.started_at, interview.ended_at);
          const duration = minutes !== null ? `${minutes} min` : null;
          return (
            <li key={interview.id} className={styles.row}>
              <div className={styles.main}>
                <p className={styles.title}>
                  {repositories ? (
                    <span className={styles.repo}>{names.get(interview.repository_id) ?? "Repository"}</span>
                  ) : (
                    <span className={styles.date}>{when}</span>
                  )}
                  <span className={`${styles.outcome} ${outcome.tone}`}>{outcome.label}</span>
                </p>
                <p className={styles.meta}>{[repositories ? when : null, duration].filter(Boolean).join(" · ")}</p>
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

import type { Repository } from "../../api/types";
import { ButtonLink } from "../../components/Button";
import { Card } from "../../components/Card";
import { formatDate, repoName } from "../../lib/format";
import { StatusChip } from "./StatusChip";
import styles from "./RepositoryList.module.css";

const HINTS: Partial<Record<Repository["status"], string>> = {
  queued: "Waiting to be indexed",
  in_progress: "Indexing your code, usually a few minutes. You can leave this page.",
};

export function RepositoryList({ repositories }: { repositories: Repository[] }) {
  return (
    <Card>
      <ul className={styles.list} aria-label="Repositories">
        {repositories.map((repo) => {
          const { owner, name } = repoName(repo.github_url);
          const hint = repo.status === "failed" ? repo.error_message ?? "Indexing failed." : HINTS[repo.status];
          return (
            <li key={repo.id} className={styles.row}>
              <div className={styles.main}>
                <div className={styles.titleLine}>
                  <a className={styles.name} href={repo.github_url} target="_blank" rel="noreferrer">
                    {owner && <span className={styles.owner}>{owner}/</span>}
                    {name}
                  </a>
                  <StatusChip status={repo.status} />
                </div>
                <p className={repo.status === "failed" ? styles.error : styles.meta}>
                  {hint ?? `Added ${formatDate(repo.created_at)}`}
                </p>
              </div>
              {repo.status === "ready" ? (
                <ButtonLink to={`/repositories/${repo.id}/interview`} className={styles.action}>
                  Start interview
                </ButtonLink>
              ) : (
                <ButtonLink to={`/repositories/${repo.id}`} variant="ghost" className={styles.action}>
                  Details
                </ButtonLink>
              )}
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

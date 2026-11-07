import { useState } from "react";
import { Link } from "react-router-dom";
import type { Interview, Repository } from "../../api/types";
import { Button } from "../../components/Button";
import { ErrorDetails } from "../../components/ErrorDetails";
import { Icon } from "../../components/Icon";
import { ProgressBar } from "../../components/ProgressBar";
import { formatDate, formatRelative, repoName } from "../../lib/format";
import { isIndexing, retryRepository } from "./api";
import { PROBLEM_TITLE, repositoryProblem } from "./problem";
import { StatusChip } from "./StatusChip";
import styles from "./RepositoryList.module.css";

/** One compact card per repository, its next step at the bottom. */
export function RepositoryList({
  repositories,
  interviews = [],
  onChanged,
}: {
  repositories: Repository[];
  interviews?: Interview[];
  onChanged?: () => void;
}) {
  return (
    <ul className={styles.grid} aria-label="Repositories">
      {repositories.map((repo) => (
        <li key={repo.id} className={styles.card}>
          <RepositoryCard
            repository={repo}
            interviews={interviews.filter((i) => i.repository_id === repo.id)}
            onChanged={onChanged}
          />
        </li>
      ))}
    </ul>
  );
}

/** The whole card opens the repository's page, where the interview starts:
 * one way in, not a second Start button here. */
function RepositoryCard({
  repository,
  interviews,
  onChanged,
}: {
  repository: Repository;
  interviews: Interview[];
  onChanged?: () => void;
}) {
  const { owner, name } = repoName(repository.github_url);
  const count = interviews.length;
  const meta = [
    count > 0 && `${count} ${count === 1 ? "interview" : "interviews"}`,
    `Added ${formatDate(repository.created_at)}`,
  ].filter(Boolean);

  return (
    <>
      <div className={styles.head}>
        <Link to={`/repositories/${repository.id}`} className={styles.name}>
          <Icon name="repo" size={16} className={styles.repoIcon} />
          {name}
        </Link>
        <StatusChip status={repository.status} />
      </div>
      <p className={styles.path}>{owner ? `github.com/${owner}/${name}` : repository.github_url}</p>
      <p className={styles.meta}>{meta.join(" · ")}</p>

      <div className={styles.foot}>
        {repository.status === "ready" ? (
          <p className={styles.next}>
            <span>{lastPracticed(interviews)}</span>
            <span className={styles.open} aria-hidden="true">
              Open
              <Icon name="arrow" size={16} />
            </span>
          </p>
        ) : isIndexing(repository.status) ? (
          <div className={styles.preparing}>
            <ProgressBar label="Preparing" />
            <span>Usually a few minutes</span>
          </div>
        ) : (
          <FailedFoot repository={repository} onChanged={onChanged} />
        )}
      </div>
    </>
  );
}

function lastPracticed(interviews: Interview[]): string {
  const latest = interviews
    .map((i) => i.started_at)
    .filter((d): d is string => d !== null)
    .sort()
    .at(-1);
  return latest ? `Last practiced ${formatRelative(latest)}` : "Not practiced yet";
}

function FailedFoot({ repository, onChanged }: { repository: Repository; onChanged?: () => void }) {
  const [retrying, setRetrying] = useState(false);
  const [error, setError] = useState(false);
  const problem = repositoryProblem(repository.error_message);

  async function handleRetry() {
    setRetrying(true);
    setError(false);
    try {
      await retryRepository(repository.id);
      onChanged?.();
    } catch {
      setError(true);
      setRetrying(false);
    }
  }

  return (
    <div className={styles.failed}>
      <p className={styles.problem}>
        <Icon name="alert" size={16} />
        {error ? "Couldn't retry just now. Try again in a minute." : `${PROBLEM_TITLE}.`}
      </p>
      <div className={styles.actions}>
        {problem.retryable && (
          <Button variant="secondary" onClick={handleRetry} disabled={retrying}>
            {retrying ? "Retrying…" : "Retry"}
          </Button>
        )}
        <ErrorDetails technical={repository.error_message}>{problem.reason}</ErrorDetails>
      </div>
    </div>
  );
}

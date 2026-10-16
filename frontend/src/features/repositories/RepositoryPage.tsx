import { useCallback } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { ApiError } from "../../api/client";
import type { Repository } from "../../api/types";
import { ButtonLink } from "../../components/Button";
import { Card } from "../../components/Card";
import { ConnectionProblem } from "../../components/ConnectionProblem";
import { EmptyState } from "../../components/EmptyState";
import { ProgressBar } from "../../components/ProgressBar";
import { PageSpinner } from "../../components/Spinner";
import { usePolling } from "../../hooks/usePolling";
import { useResource } from "../../hooks/useResource";
import { formatRelative, repoName } from "../../lib/format";
import { getRepository, isIndexing } from "./api";
import { repositoryProblem } from "./problem";
import { StatusChip } from "./StatusChip";
import styles from "./RepositoryPage.module.css";

const POLL_MS = 2000;

/** One repository's indexing status, then the way into an interview. */
export function RepositoryPage() {
  const id = Number(useParams().id);
  const alreadyConnected = Boolean((useLocation().state as { alreadyConnected?: boolean } | null)?.alreadyConnected);
  const load = useCallback(() => getRepository(id), [id]);
  const repo = useResource(load);
  usePolling(repo.reload, POLL_MS, repo.state === "ready" && isIndexing(repo.data.status));

  if (repo.state === "loading") return <PageSpinner />;
  if (repo.state === "error") {
    if (repo.error instanceof ApiError && (repo.error.status === 404 || repo.error.status === 422)) {
      return (
        <EmptyState title="Repository not found" action={<ButtonLink to="/home">Back to home</ButtonLink>}>
          It may have been removed, or it belongs to another account.
        </EmptyState>
      );
    }
    return <ConnectionProblem onRetry={repo.reload} />;
  }

  const { owner, name } = repoName(repo.data.github_url);

  return (
    <div className={styles.page}>
      <Link to="/home" className={styles.back}>
        ← Home
      </Link>

      <header className={styles.header}>
        <h1 className={styles.title}>
          {owner && <span className={styles.owner}>{owner}/</span>}
          {name}
        </h1>
        <a href={repo.data.github_url} target="_blank" rel="noreferrer" className={styles.github}>
          View on GitHub ↗
        </a>
      </header>

      {alreadyConnected && (
        <p className={styles.notice} role="status">
          You&rsquo;ve already connected this repository.
        </p>
      )}

      <Card className={styles.card}>
        <StatusPanel repository={repo.data} />
      </Card>
    </div>
  );
}

function StatusPanel({ repository }: { repository: Repository }) {
  const { status } = repository;

  if (isIndexing(status)) {
    return (
      <div className={styles.panel} aria-live="polite">
        <div className={styles.panelHead}>
          <h2 className={styles.panelTitle}>{status === "queued" ? "Waiting to start" : "Reading your code"}</h2>
          <StatusChip status={status} />
        </div>
        <ProgressBar label="Reading your code" />
        <p className={styles.body}>
          Usually a few minutes. You can leave this page; it carries on, and the repository will show as ready on
          your home page.
        </p>
        <p className={styles.meta}>Started {formatRelative(repository.created_at)}</p>
      </div>
    );
  }

  if (status === "ready") {
    return (
      <div className={styles.panel} aria-live="polite">
        <div className={styles.panelHead}>
          <h2 className={styles.panelTitle}>Ready for an interview</h2>
          <StatusChip status={status} />
        </div>
        <p className={styles.body}>
          Up to six spoken questions, each about a different part of this project. About 15 minutes, and you can
          stop at any point.
        </p>
        <div className={styles.actions}>
          <ButtonLink to={`/repositories/${repository.id}/interview`} size="large">
            Start interview
          </ButtonLink>
          <ButtonLink to="/home" variant="ghost">
            Not now
          </ButtonLink>
        </div>
      </div>
    );
  }

  const problem = repositoryProblem(repository.error_message);
  return (
    <div className={styles.panel} aria-live="polite">
      <div className={styles.panelHead}>
        <h2 className={styles.panelTitle}>{problem.title}</h2>
        <StatusChip status={status} />
      </div>
      <p className={styles.body}>{problem.body}</p>
      <div className={styles.actions}>
        <ButtonLink to="/repositories/new">Connect a repository</ButtonLink>
        <ButtonLink to="/home" variant="ghost">
          Back to home
        </ButtonLink>
      </div>
    </div>
  );
}

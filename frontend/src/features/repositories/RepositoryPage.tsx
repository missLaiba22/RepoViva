import { useCallback, useState } from "react";
import { useLocation, useParams } from "react-router-dom";
import { ApiError } from "../../api/client";
import { listInterviews } from "../../api/interviews";
import type { Repository } from "../../api/types";
import { Button, ButtonLink } from "../../components/Button";
import { Card } from "../../components/Card";
import { ConnectionProblem } from "../../components/ConnectionProblem";
import { EmptyState } from "../../components/EmptyState";
import { Facts } from "../../components/Facts";
import { ErrorDetails } from "../../components/ErrorDetails";
import { Icon } from "../../components/Icon";
import { InterviewList } from "../../components/InterviewList";
import { PageHeader } from "../../components/PageHeader";
import { ProgressBar } from "../../components/ProgressBar";
import { RepoName } from "../../components/RepoName";
import { PageSpinner } from "../../components/Spinner";
import { usePolling } from "../../hooks/usePolling";
import { useResource } from "../../hooks/useResource";
import { REPOSITORIES_CRUMB } from "../../lib/crumbs";
import { INTERVIEW_FACTS } from "../../lib/interviewFacts";
import { formatRelative, repoName } from "../../lib/format";
import { getRepository, isIndexing, retryRepository } from "./api";
import { PROBLEM_TITLE, repositoryProblem } from "./problem";
import { StatusChip } from "./StatusChip";
import styles from "./RepositoryPage.module.css";

const POLL_MS = 2000;

/** One repository's home: its status, the way into an interview, and its
 * past interviews with their reports. */
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
        <EmptyState title="Repository not found" action={<ButtonLink to="/repositories">Back to repositories</ButtonLink>}>
          It may have been removed, or it belongs to another account.
        </EmptyState>
      );
    }
    return <ConnectionProblem onRetry={repo.reload} />;
  }

  return (
    <div className={styles.page}>
      <PageHeader
        crumbs={[REPOSITORIES_CRUMB]}
        title={<RepoName githubUrl={repo.data.github_url} />}
        lead={<GitHubLink githubUrl={repo.data.github_url} />}
      />

      {alreadyConnected && (
        <p className={styles.notice} role="status">
          You&rsquo;ve already connected this repository.
        </p>
      )}

      <Card className={styles.card}>
        <StatusPanel repository={repo.data} onRetried={repo.set} />
      </Card>

      {repo.data.status === "ready" && <PastInterviews repositoryId={repo.data.id} />}
    </div>
  );
}

/** Quietly absent if the list can't load: the page's job is the status. */
function PastInterviews({ repositoryId }: { repositoryId: number }) {
  const load = useCallback(
    () => listInterviews().then((all) => all.filter((i) => i.repository_id === repositoryId)),
    [repositoryId],
  );
  const interviews = useResource(load);
  if (interviews.state !== "ready") return null;

  return (
    <section className={styles.section} aria-labelledby="past-heading">
      <h2 id="past-heading" className={styles.sectionTitle}>
        Your interviews
      </h2>
      {interviews.data.length === 0 ? (
        <p className={styles.none}>No interviews yet</p>
      ) : (
        <InterviewList interviews={interviews.data} label="Your interviews" />
      )}
    </section>
  );
}

function GitHubLink({ githubUrl }: { githubUrl: string }) {
  const { owner, name } = repoName(githubUrl);
  return (
    <a href={githubUrl} target="_blank" rel="noreferrer" className={styles.github}>
      {owner ? `github.com/${owner}/${name}` : githubUrl}
      <Icon name="external" size={14} />
    </a>
  );
}

function StatusPanel({ repository, onRetried }: { repository: Repository; onRetried: (repo: Repository) => void }) {
  const { status } = repository;

  if (isIndexing(status)) {
    return (
      <div className={styles.panel} aria-live="polite">
        <div className={styles.panelHead}>
          <h2 className={styles.panelTitle}>Preparing your repository</h2>
          <StatusChip status={status} />
        </div>
        <ProgressBar label="Preparing" />
        <p className={styles.meta}>
          Started {formatRelative(repository.created_at)} · usually a few minutes · you can leave this page
        </p>
      </div>
    );
  }

  if (status === "ready") {
    return (
      <div className={styles.panel} aria-live="polite">
        <h2 className={styles.panelTitle}>Ready to practice</h2>
        <Facts items={INTERVIEW_FACTS} label="About the interview" />
        <div className={styles.actions}>
          <ButtonLink to={`/repositories/${repository.id}/interview`} size="large">
            Start interview
            <Icon name="arrow" size={18} />
          </ButtonLink>
        </div>
      </div>
    );
  }

  return <FailedPanel repository={repository} onRetried={onRetried} />;
}

function FailedPanel({ repository, onRetried }: { repository: Repository; onRetried: (repo: Repository) => void }) {
  const [retrying, setRetrying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const problem = repositoryProblem(repository.error_message);

  async function handleRetry() {
    setRetrying(true);
    setError(null);
    try {
      onRetried(await retryRepository(repository.id));
    } catch {
      setError("Couldn't retry just now. Try again in a minute.");
      setRetrying(false);
    }
  }

  return (
    <div className={styles.panel} aria-live="polite">
      <div className={styles.panelHead}>
        <h2 className={styles.panelTitle}>{PROBLEM_TITLE}</h2>
        <StatusChip status={repository.status} />
      </div>
      <p className={styles.body}>{problem.reason}</p>
      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}
      <div className={styles.actions}>
        {problem.retryable ? (
          <Button onClick={handleRetry} disabled={retrying}>
            {retrying ? "Retrying…" : "Retry"}
          </Button>
        ) : (
          <ButtonLink to="/repositories/new">Connect a different repository</ButtonLink>
        )}
        <ErrorDetails technical={repository.error_message} />
      </div>
    </div>
  );
}

import { useCallback, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
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
import { RepositoryOverview } from "./RepositoryOverview";
import { StatusChip } from "./StatusChip";
import styles from "./RepositoryPage.module.css";

const POLL_MS = 2000;

/** One repository's home and the one place an interview starts: its status,
 * what was analyzed, and its latest interviews. */
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
        <EmptyState icon="repo" title="Repository not found" action={<ButtonLink to="/repositories">Back to repositories</ButtonLink>}>
          It may have been removed, or it belongs to another account.
        </EmptyState>
      );
    }
    return <ConnectionProblem error={repo.error} onRetry={repo.reload} />;
  }

  const ready = repo.data.status === "ready";

  return (
    <div className={styles.page}>
      <PageHeader
        crumbs={[REPOSITORIES_CRUMB]}
        title={<RepoName githubUrl={repo.data.github_url} />}
        lead={
          <div className={styles.lead}>
            <GitHubLink githubUrl={repo.data.github_url} />
            {ready && <Facts items={INTERVIEW_FACTS} label="About the interview" />}
          </div>
        }
        actions={
          ready && (
            <ButtonLink to={`/repositories/${repo.data.id}/interview`} size="large">
              Start interview
              <Icon name="arrow" size={18} />
            </ButtonLink>
          )
        }
      />

      {alreadyConnected && (
        <p className={styles.notice} role="status">
          You&rsquo;ve already connected this repository.
        </p>
      )}

      {ready ? (
        <>
          <RepositoryOverview repository={repo.data} />
          <RecentInterviews repositoryId={repo.data.id} />
        </>
      ) : (
        <Card className={styles.card}>
          <StatusPanel repository={repo.data} onRetried={repo.set} />
        </Card>
      )}
    </div>
  );
}

const RECENT = 3;

/** The latest few; the Reports page holds the full history. Quietly absent
 * if the list can't load: the page's job is the repository. */
function RecentInterviews({ repositoryId }: { repositoryId: number }) {
  const load = useCallback(
    () => listInterviews().then((all) => all.filter((i) => i.repository_id === repositoryId)),
    [repositoryId],
  );
  const interviews = useResource(load);
  if (interviews.state !== "ready") return null;
  const all = interviews.data;

  return (
    <section className={styles.section} aria-labelledby="past-heading">
      <div className={styles.sectionHead}>
        <h2 id="past-heading" className={styles.sectionTitle}>
          Recent interviews
        </h2>
        {all.length > RECENT && (
          <Link to={`/interviews?repository=${repositoryId}`} className={styles.seeAll}>
            All {all.length} in Reports
            <Icon name="arrow" size={14} />
          </Link>
        )}
      </div>
      {all.length === 0 ? (
        <p className={styles.none}>No interviews yet. Your reports will appear here.</p>
      ) : (
        <InterviewList interviews={all.slice(0, RECENT)} label="Recent interviews" />
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

const STAGES = ["Waiting to start", "Reading and indexing your code", "Ready to practice"];

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
        <ol className={styles.stages} aria-label="Preparation stages">
          {STAGES.map((stage, index) => {
            const at = status === "queued" ? 0 : 1;
            const state = index < at ? "done" : index === at ? "now" : "todo";
            return (
              <li key={stage} className={styles[state]} aria-current={state === "now" ? "step" : undefined}>
                <span className={styles.stageDot} aria-hidden="true">
                  {state === "done" && <Icon name="check" size={12} />}
                </span>
                {stage}
              </li>
            );
          })}
        </ol>
        <p className={styles.meta}>
          Started {formatRelative(repository.created_at)} · usually a few minutes · you can leave this page, it
          keeps going
        </p>
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

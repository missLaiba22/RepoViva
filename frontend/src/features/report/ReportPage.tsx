import { useCallback, useState, type ReactNode } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError } from "../../api/client";
import type { Interview, Report, TurnEvaluation } from "../../api/types";
import { Button, ButtonLink } from "../../components/Button";
import { Card } from "../../components/Card";
import { ConnectionProblem } from "../../components/ConnectionProblem";
import { EmptyState } from "../../components/EmptyState";
import { PageHeader } from "../../components/PageHeader";
import { ProgressBar } from "../../components/ProgressBar";
import { PageSpinner } from "../../components/Spinner";
import { usePolling } from "../../hooks/usePolling";
import { useResource } from "../../hooks/useResource";
import { REPORTS_CRUMB } from "../../lib/crumbs";
import { durationMinutes, formatDateTime, repoName } from "../../lib/format";
import { getReport, hasEnded, loadReportContext, retryReport, type ReportContext } from "./api";
import { FilesToRevisit, SummaryPanel } from "./SummaryPanel";
import { TurnList } from "./TurnList";
import styles from "./ReportPage.module.css";

const POLL_MS = 4000;

export function ReportPage() {
  const id = Number(useParams().id);
  const load = useCallback(() => loadReportContext(id), [id]);
  const context = useResource(load);

  if (context.state === "loading") return <PageSpinner />;
  if (context.state === "error") {
    if (context.error instanceof ApiError && (context.error.status === 404 || context.error.status === 422)) {
      return (
        <EmptyState title="Report not found" action={<ButtonLink to="/interviews">All reports</ButtonLink>}>
          This interview doesn&rsquo;t exist, or it belongs to another account.
        </EmptyState>
      );
    }
    return <ConnectionProblem onRetry={context.reload} />;
  }

  return (
    <div className={styles.page}>
      <Header context={context.data} />
      {hasEnded(context.data.interview) ? (
        <ReportBody context={context.data} />
      ) : (
        <EmptyState title="This interview hasn't finished" action={<ButtonLink to="/interviews">All reports</ButtonLink>}>
          The report is written once the interview ends.
        </EmptyState>
      )}
    </div>
  );
}

function Header({ context }: { context: ReportContext }) {
  const { interview, repository } = context;
  const { name } = repoName(repository.github_url);
  const minutes = durationMinutes(interview.started_at, interview.ended_at);
  return (
    <PageHeader
      crumbs={[REPORTS_CRUMB]}
      title="Interview report"
      lead={
        <p className={styles.meta}>
          <Link to={`/repositories/${repository.id}`} className={styles.repo}>
            {name}
          </Link>
          <span aria-hidden="true">·</span>
          {formatDateTime(interview.started_at ?? interview.created_at)}
          {minutes !== null && ` · ${minutes} min`}
          {interview.status === "interrupted" && <span className={styles.badge}>Ended early</span>}
        </p>
      }
      actions={
        repository.status === "ready" && (
          <ButtonLink to={`/repositories/${repository.id}/interview`} variant="secondary">
            Practise again
          </ButtonLink>
        )
      }
    />
  );
}

function ReportBody({ context }: { context: ReportContext }) {
  const { interview, repository } = context;
  const load = useCallback(() => getReport(interview.id), [interview.id]);
  const report = useResource(load);
  const generating = report.state === "ready" && report.data.status === "generating";
  usePolling(report.reload, POLL_MS, generating);

  if (report.state === "loading") return <PageSpinner />;
  if (report.state === "error") return <ConnectionProblem onRetry={report.reload} />;

  const data = report.data;
  if (data.status === "generating") return <Generating />;
  if (data.status === "failed") return <Failed interview={interview} onRetried={report.set} />;

  const turns = data.turn_evaluations ?? [];
  const strong = turns.filter(isStrong);
  const revisit = turns.filter((t) => t.status !== "not_answered" && !isStrong(t));
  const unanswered = turns.filter((t) => t.status === "not_answered");
  const files = data.summary?.files_to_revisit ?? [];

  return (
    <>
      {data.summary && <SummaryPanel summary={data.summary} />}

      {strong.length > 0 && (
        <Section id="strong" title="Strong answers" count={strong.length}>
          <TurnList turns={strong} githubUrl={repository.github_url} label="Strong answers" />
        </Section>
      )}

      {revisit.length > 0 && (
        <Section id="revisit" title="Answers to revisit" count={revisit.length}>
          <TurnList turns={revisit} githubUrl={repository.github_url} label="Answers to revisit" />
        </Section>
      )}

      {files.length > 0 && (
        <Section id="files" title="Files to revisit" count={files.length}>
          <FilesToRevisit files={files} githubUrl={repository.github_url} />
        </Section>
      )}

      {unanswered.length > 0 && (
        <Section id="unanswered" title="Not reached" count={unanswered.length}>
          <TurnList turns={unanswered} githubUrl={repository.github_url} label="Not reached" />
        </Section>
      )}

      <footer className={styles.footer}>
        <div className={styles.actions}>
          <ButtonLink to={`/repositories/${repository.id}/interview`}>Practise again</ButtonLink>
          <ButtonLink to="/interviews" variant="ghost">
            All reports
          </ButtonLink>
        </div>
        <p className={styles.fine}>Feedback is AI-written from your code. Treat it as a study guide, not a verdict.</p>
      </footer>
    </>
  );
}

/** Both scores at 4 or more out of 5. */
function isStrong(turn: TurnEvaluation): boolean {
  return turn.status === "graded" && turn.correctness.score >= 4 && turn.clarity.score >= 4;
}

function Section({ id, title, count, children }: { id: string; title: string; count: number; children: ReactNode }) {
  const headingId = `${id}-heading`;
  return (
    <section className={styles.section} aria-labelledby={headingId}>
      <h2 id={headingId} className={styles.sectionTitle}>
        {title}
        <span className={styles.count}>{count}</span>
      </h2>
      {children}
    </section>
  );
}

function Generating() {
  return (
    <Card className={styles.state} aria-live="polite">
      <h2 className={styles.stateTitle}>Grading your answers</h2>
      <ProgressBar label="Grading" />
      <p className={styles.stateText}>
        Checking each answer against your code. Usually about a minute; you can leave this page.
      </p>
    </Card>
  );
}

function Failed({ interview, onRetried }: { interview: Interview; onRetried: (report: Report) => void }) {
  const [retrying, setRetrying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleRetry() {
    setRetrying(true);
    setError(null);
    try {
      onRetried(await retryReport(interview.id));
    } catch {
      setError("That didn't work either. Try again later.");
      setRetrying(false);
    }
  }

  return (
    <Card className={styles.state}>
      <h2 className={styles.stateTitle}>This report couldn&rsquo;t be finished</h2>
      <p className={styles.stateText}>
        Usually temporary. Your answers are saved.
      </p>
      {error && (
        <p className={styles.error} role="alert">
          {error}
        </p>
      )}
      <div>
        <Button onClick={handleRetry} disabled={retrying}>
          {retrying ? "Starting…" : "Try grading again"}
        </Button>
      </div>
    </Card>
  );
}

import { useCallback, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { ApiError } from "../../api/client";
import type { Interview, Report } from "../../api/types";
import { Button, ButtonLink } from "../../components/Button";
import { Card } from "../../components/Card";
import { ConnectionProblem } from "../../components/ConnectionProblem";
import { EmptyState } from "../../components/EmptyState";
import { ProgressBar } from "../../components/ProgressBar";
import { PageSpinner } from "../../components/Spinner";
import { usePolling } from "../../hooks/usePolling";
import { useResource } from "../../hooks/useResource";
import { durationMinutes, formatDateTime, repoName } from "../../lib/format";
import { getReport, hasEnded, loadReportContext, retryReport, type ReportContext } from "./api";
import { SummaryPanel } from "./SummaryPanel";
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
        <EmptyState title="Report not found" action={<ButtonLink to="/home">Back to home</ButtonLink>}>
          This interview doesn&rsquo;t exist, or it belongs to another account.
        </EmptyState>
      );
    }
    return <ConnectionProblem onRetry={context.reload} />;
  }

  return (
    <div className={styles.page}>
      <Link to="/home" className={styles.back}>
        ← Home
      </Link>
      <Header context={context.data} />
      {hasEnded(context.data.interview) ? (
        <ReportBody context={context.data} />
      ) : (
        <EmptyState title="This interview hasn't finished" action={<ButtonLink to="/home">Back to home</ButtonLink>}>
          The report is written once the interview ends.
        </EmptyState>
      )}
    </div>
  );
}

function Header({ context }: { context: ReportContext }) {
  const { interview, repository } = context;
  const { owner, name } = repoName(repository.github_url);
  const minutes = durationMinutes(interview.started_at, interview.ended_at);
  return (
    <header className={styles.header}>
      <p className={styles.eyebrow}>Interview report</p>
      <h1 className={styles.title}>
        {owner && <span className={styles.owner}>{owner}/</span>}
        {name}
      </h1>
      <p className={styles.meta}>
        {formatDateTime(interview.started_at ?? interview.created_at)}
        {minutes !== null && ` · ${minutes} min`}
        {interview.status === "interrupted" && <span className={styles.badge}>Ended early</span>}
      </p>
    </header>
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

  return (
    <>
      {data.summary && <SummaryPanel summary={data.summary} githubUrl={repository.github_url} />}

      {data.turn_evaluations && data.turn_evaluations.length > 0 && (
        <section className={styles.section} aria-labelledby="turns-heading">
          <div className={styles.sectionHead}>
            <h2 id="turns-heading" className={styles.sectionTitle}>
              Question by question
            </h2>
            <p className={styles.sectionHint}>Open a question for the feedback and the code behind it.</p>
          </div>
          <TurnList turns={data.turn_evaluations} githubUrl={repository.github_url} />
        </section>
      )}

      <footer className={styles.footer}>
        <div className={styles.actions}>
          <ButtonLink to={`/repositories/${repository.id}/interview`}>Practise again</ButtonLink>
          <ButtonLink to="/home" variant="ghost">
            Back to home
          </ButtonLink>
        </div>
        <p className={styles.fine}>
          Each answer is checked against the code its question was built from, by{" "}
          {data.model?.replace(/^groq\//, "") ?? "an AI grader"}
          {data.prompt_version && ` (prompt ${data.prompt_version})`}. It can miss things, so treat it as a study
          guide, not a verdict.
        </p>
      </footer>
    </>
  );
}

function Generating() {
  return (
    <Card className={styles.state} aria-live="polite">
      <h2 className={styles.stateTitle}>Grading your answers</h2>
      <ProgressBar label="Grading" />
      <p className={styles.stateText}>
        Each answer is being checked against your code. This usually takes about a minute. You can leave; the report
        will be here when you come back.
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
      setError("Grading is unavailable right now. Please try again in a little while.");
      setRetrying(false);
    }
  }

  return (
    <Card className={styles.state}>
      <h2 className={styles.stateTitle}>This report couldn&rsquo;t be finished</h2>
      <p className={styles.stateText}>
        Grading stopped partway, most often because the grading service hit its daily limit. Your answers are saved,
        so it can simply run again.
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

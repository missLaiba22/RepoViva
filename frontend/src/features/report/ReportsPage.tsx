import { listInterviews } from "../../api/interviews";
import { ButtonLink } from "../../components/Button";
import { ConnectionProblem } from "../../components/ConnectionProblem";
import { EmptyState } from "../../components/EmptyState";
import { InterviewList } from "../../components/InterviewList";
import { PageHeader } from "../../components/PageHeader";
import { PageSpinner } from "../../components/Spinner";
import { useResource } from "../../hooks/useResource";
import { listRepositories } from "../repositories";
import styles from "./ReportsPage.module.css";

/** Never reads reports: reading one for an ended interview with none makes
 * Core API trigger grading, which costs real tokens. */
async function loadReports() {
  const [interviews, repositories] = await Promise.all([listInterviews(), listRepositories()]);
  return { interviews, repositories };
}

/** Every interview the user has taken, newest first, each with its report. */
export function ReportsPage() {
  const page = useResource(loadReports);

  if (page.state === "loading") return <PageSpinner />;
  if (page.state === "error") return <ConnectionProblem onRetry={page.reload} />;

  const { interviews, repositories } = page.data;

  return (
    <div className={styles.page}>
      <PageHeader title="Reports" />
      {interviews.length === 0 ? (
        <EmptyState
          title="No reports yet"
          action={<ButtonLink to="/repositories">Choose a repository</ButtonLink>}
        >
          Each interview you finish gets a report here.
        </EmptyState>
      ) : (
        <InterviewList interviews={interviews} repositories={repositories} label="Reports" />
      )}
    </div>
  );
}

import { Link, useSearchParams } from "react-router-dom";
import { listInterviews } from "../../api/interviews";
import type { Repository } from "../../api/types";
import { ButtonLink } from "../../components/Button";
import { ConnectionProblem } from "../../components/ConnectionProblem";
import { EmptyState } from "../../components/EmptyState";
import { InterviewList } from "../../components/InterviewList";
import { PageHeader } from "../../components/PageHeader";
import { PageSpinner } from "../../components/Spinner";
import { useResource } from "../../hooks/useResource";
import { repoName } from "../../lib/format";
import { listRepositories } from "../repositories";
import styles from "./ReportsPage.module.css";

/** Never reads reports: reading one for an ended interview with none makes
 * Core API trigger grading, which costs real tokens. */
async function loadReports() {
  const [interviews, repositories] = await Promise.all([listInterviews(), listRepositories()]);
  return { interviews, repositories };
}

/** Every interview the user has taken, newest first, each opening its
 * report; `?repository=<id>` narrows it to one repository. */
export function ReportsPage() {
  const page = useResource(loadReports);
  const [params] = useSearchParams();

  if (page.state === "loading") return <PageSpinner />;
  if (page.state === "error") return <ConnectionProblem error={page.error} onRetry={page.reload} />;

  const { interviews, repositories } = page.data;
  const practiced = repositories.filter((r) => interviews.some((i) => i.repository_id === r.id));
  const selected = practiced.find((r) => String(r.id) === params.get("repository"));
  const shown = selected ? interviews.filter((i) => i.repository_id === selected.id) : interviews;

  return (
    <div className={styles.page}>
      <PageHeader title="Reports" lead="Open an interview to see how you did and what a strong answer covers." />
      {interviews.length === 0 ? (
        <EmptyState
          icon="report"
          title="No reports yet"
          action={<ButtonLink to="/repositories">Choose a repository</ButtonLink>}
        >
          Each interview you finish gets a report here.
        </EmptyState>
      ) : (
        <div className={styles.results}>
          {practiced.length > 1 && <RepositoryFilter repositories={practiced} selected={selected} />}
          <InterviewList interviews={shown} repositories={repositories} label="Reports" />
        </div>
      )}
    </div>
  );
}

function RepositoryFilter({ repositories, selected }: { repositories: Repository[]; selected?: Repository }) {
  return (
    <nav aria-label="Filter by repository">
      <ul className={styles.filters}>
        <li>
          <Link to="/interviews" className={styles.filter} aria-current={selected ? undefined : "page"}>
            All
          </Link>
        </li>
        {repositories.map((repo) => (
          <li key={repo.id}>
            <Link
              to={`/interviews?repository=${repo.id}`}
              className={styles.filter}
              aria-current={selected?.id === repo.id ? "page" : undefined}
            >
              {repoName(repo.github_url).name}
            </Link>
          </li>
        ))}
      </ul>
    </nav>
  );
}

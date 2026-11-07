import { ConnectionProblem } from "../../components/ConnectionProblem";
import { PageHeader } from "../../components/PageHeader";
import { PageSpinner } from "../../components/Spinner";
import { usePolling } from "../../hooks/usePolling";
import { useResource } from "../../hooks/useResource";
import { useAuth } from "../auth/authContext";
import { isIndexing, loadRepositoriesPage } from "./api";
import { GettingStarted } from "./GettingStarted";
import { RepositoryList } from "./RepositoryList";
import styles from "./RepositoriesPage.module.css";

const POLL_MS = 3000;

export function RepositoriesPage() {
  const auth = useAuth();
  const page = useResource(loadRepositoriesPage);
  const anyIndexing = page.state === "ready" && page.data.repositories.some((r) => isIndexing(r.status));
  usePolling(page.reload, POLL_MS, anyIndexing);

  if (page.state === "loading") return <PageSpinner />;
  if (page.state === "error") return <ConnectionProblem error={page.error} onRetry={page.reload} />;

  const { repositories, interviews } = page.data;
  const firstRun = !interviews.some((i) => i.status === "completed" || i.status === "interrupted");

  return (
    <div className={styles.page}>
      <PageHeader title="Repositories" />

      {firstRun && (
        <GettingStarted login={auth.user?.github_login} repositories={repositories} interviews={interviews} />
      )}
      {repositories.length > 0 && (
        <RepositoryList repositories={repositories} interviews={interviews} onChanged={page.reload} />
      )}
    </div>
  );
}

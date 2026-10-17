import { ButtonLink } from "../../components/Button";
import { ConnectionProblem } from "../../components/ConnectionProblem";
import { EmptyState } from "../../components/EmptyState";
import { PageHeader } from "../../components/PageHeader";
import { PageSpinner } from "../../components/Spinner";
import { usePolling } from "../../hooks/usePolling";
import { useResource } from "../../hooks/useResource";
import { isIndexing, loadRepositoriesPage } from "./api";
import { RepositoryList } from "./RepositoryList";
import styles from "./RepositoriesPage.module.css";

const POLL_MS = 3000;

export function RepositoriesPage() {
  const page = useResource(loadRepositoriesPage);
  const anyIndexing = page.state === "ready" && page.data.repositories.some((r) => isIndexing(r.status));
  usePolling(page.reload, POLL_MS, anyIndexing);

  if (page.state === "loading") return <PageSpinner />;
  if (page.state === "error") return <ConnectionProblem onRetry={page.reload} />;

  const { repositories, interviews } = page.data;

  return (
    <div className={styles.page}>
      <PageHeader title="Repositories" />

      {repositories.length === 0 ? (
        <EmptyState
          title="Connect your first repository"
          action={<ButtonLink to="/repositories/new">Connect repository</ButtonLink>}
        >
          Paste a public GitHub link. You&rsquo;ll be interviewed about that code.
        </EmptyState>
      ) : (
        <RepositoryList repositories={repositories} interviews={interviews} onChanged={page.reload} />
      )}
    </div>
  );
}

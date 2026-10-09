import { ButtonLink } from "../../components/Button";
import { ConnectionProblem } from "../../components/ConnectionProblem";
import { EmptyState } from "../../components/EmptyState";
import { PageSpinner } from "../../components/Spinner";
import { usePolling } from "../../hooks/usePolling";
import { useResource } from "../../hooks/useResource";
import { useAuth } from "../auth";
import { RepositoryList, isIndexing } from "../repositories";
import { loadHome } from "./api";
import { RecentInterviews } from "./RecentInterviews";
import styles from "./HomePage.module.css";

const POLL_MS = 3000;

export function HomePage() {
  const { user } = useAuth();
  const home = useResource(loadHome);
  const anyIndexing = home.state === "ready" && home.data.repositories.some((r) => isIndexing(r.status));
  usePolling(home.reload, POLL_MS, anyIndexing);

  if (home.state === "loading") return <PageSpinner />;
  if (home.state === "error") return <ConnectionProblem onRetry={home.reload} />;

  const { repositories, interviews } = home.data;
  const hasReady = repositories.some((r) => r.status === "ready");

  return (
    <div className={styles.page}>
      <header className={styles.intro}>
        <h1 className={styles.title}>Welcome back{user ? `, ${user.github_login}` : ""}</h1>
        <p className={styles.lead}>
          {hasReady
            ? "Pick a repository and talk through how it works. Each interview is about 15 minutes."
            : "Connect a repository to get your first interview about your own code."}
        </p>
      </header>

      <section className={styles.section} aria-labelledby="repos-heading">
        <div className={styles.sectionHead}>
          <h2 id="repos-heading" className={styles.sectionTitle}>
            Repositories
          </h2>
          {repositories.length > 0 && (
            <ButtonLink to="/repositories/new" variant="secondary">
              Connect repository
            </ButtonLink>
          )}
        </div>
        {repositories.length === 0 ? (
          <EmptyState
            title="Connect your first repository"
            action={<ButtonLink to="/repositories/new">Connect repository</ButtonLink>}
          >
            Paste a link to a public GitHub repository. RepoViva indexes the code, then interviews you about it.
          </EmptyState>
        ) : (
          <RepositoryList repositories={repositories} />
        )}
      </section>

      <section className={styles.section} aria-labelledby="interviews-heading">
        <div className={styles.sectionHead}>
          <h2 id="interviews-heading" className={styles.sectionTitle}>
            Recent interviews
          </h2>
        </div>
        {interviews.length === 0 ? (
          <p className={styles.none}>
            No interviews yet. Your reports will appear here after your first one.
          </p>
        ) : (
          <RecentInterviews interviews={interviews} repositories={repositories} />
        )}
      </section>
    </div>
  );
}

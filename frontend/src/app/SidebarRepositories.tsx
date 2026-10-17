import { useEffect } from "react";
import { NavLink } from "react-router-dom";
import type { RepositoryStatus } from "../api/types";
import { Icon } from "../components/Icon";
import { usePolling } from "../hooks/usePolling";
import { useResource } from "../hooks/useResource";
import { repoName } from "../lib/format";
import { isIndexing, listRepositories, onRepositoriesChanged } from "../features/repositories";
import styles from "./Layout.module.css";

const POLL_MS = 3000;
const SHOWN = 8;

const STATUS: Record<RepositoryStatus, string> = {
  queued: "preparing",
  in_progress: "preparing",
  ready: "ready",
  failed: "import failed",
};

/** The Repositories nav item, with a jump list of repositories and their
 * status underneath. Refreshes when one is connected or retried, and while
 * any is preparing. Quietly bare on error: the pages show their own problems. */
export function SidebarRepositories({ linkClass }: { linkClass: (active: boolean) => string }) {
  const repos = useResource(listRepositories);
  const preparing = repos.state === "ready" ? repos.data.filter((r) => isIndexing(r.status)).length : 0;
  usePolling(repos.reload, POLL_MS, preparing > 0);

  const { reload } = repos;
  useEffect(() => onRepositoriesChanged(reload), [reload]);

  const list = repos.state === "ready" ? repos.data : [];

  return (
    <div className={styles.group}>
      <NavLink to="/repositories" end className={({ isActive }) => linkClass(isActive)}>
        <Icon name="repo" size={18} />
        Repositories
        {preparing > 0 && (
          <span className={styles.badge} title={`${preparing} preparing`}>
            {preparing}
            <span className="visually-hidden"> preparing</span>
          </span>
        )}
      </NavLink>
      {list.length > 0 && (
        <ul className={styles.repos} aria-label="Your repositories">
          {list.slice(0, SHOWN).map((repo) => (
            <li key={repo.id}>
              <NavLink
                to={`/repositories/${repo.id}`}
                className={({ isActive }) => (isActive ? `${styles.repo} ${styles.repoActive}` : styles.repo)}
                title={`${repoName(repo.github_url).name}, ${STATUS[repo.status]}`}
              >
                <span className={`${styles.dot} ${styles[repo.status]}`} aria-hidden="true" />
                <span className={styles.repoName}>{repoName(repo.github_url).name}</span>
                <span className="visually-hidden"> ({STATUS[repo.status]})</span>
              </NavLink>
            </li>
          ))}
          {list.length > SHOWN && (
            <li>
              <NavLink to="/repositories" end className={styles.repo}>
                <span className={styles.more}>All {list.length}</span>
              </NavLink>
            </li>
          )}
        </ul>
      )}
    </div>
  );
}

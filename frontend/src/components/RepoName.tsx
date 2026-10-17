import { repoName } from "../lib/format";
import styles from "./RepoName.module.css";

/** `owner/name`, with the owner muted: how a repository is named everywhere. */
export function RepoName({ githubUrl }: { githubUrl: string }) {
  const { owner, name } = repoName(githubUrl);
  return (
    <span className={styles.repo}>
      {owner && <span className={styles.owner}>{owner}/</span>}
      {name}
    </span>
  );
}

import { Link } from "react-router-dom";
import styles from "./Logo.module.css";

export function Logo({ to = "/" }: { to?: string }) {
  return (
    <Link to={to} className={styles.logo} aria-label="RepoViva home">
      <span className={styles.mark} aria-hidden="true">
        R
      </span>
      <span className={styles.word}>RepoViva</span>
    </Link>
  );
}

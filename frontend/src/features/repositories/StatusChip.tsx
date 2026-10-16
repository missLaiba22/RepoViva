import type { RepositoryStatus } from "../../api/types";
import styles from "./StatusChip.module.css";

const LABELS: Record<RepositoryStatus, string> = {
  queued: "Waiting",
  in_progress: "Reading code",
  ready: "Ready",
  failed: "Couldn't prepare",
};

export function StatusChip({ status }: { status: RepositoryStatus }) {
  return (
    <span className={`${styles.chip} ${styles[status]}`}>
      <span className={styles.dot} aria-hidden="true" />
      {LABELS[status]}
    </span>
  );
}

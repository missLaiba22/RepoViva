import styles from "./ProgressBar.module.css";

/** An indeterminate bar: work is happening, with no reliable percentage to show. */
export function ProgressBar({ label }: { label: string }) {
  return (
    <div className={styles.track} role="progressbar" aria-label={label} aria-busy="true">
      <div className={styles.bar} />
    </div>
  );
}

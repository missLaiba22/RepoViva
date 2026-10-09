import styles from "./Spinner.module.css";

export function Spinner({ label = "Loading" }: { label?: string }) {
  return <span className={styles.spinner} role="status" aria-label={label} />;
}

export function PageSpinner({ label = "Loading" }: { label?: string }) {
  return (
    <div className={styles.page}>
      <Spinner label={label} />
    </div>
  );
}

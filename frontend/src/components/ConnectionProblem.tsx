import { Button } from "./Button";
import { EmptyState } from "./EmptyState";
import styles from "./ConnectionProblem.module.css";

export function ConnectionProblem({ onRetry }: { onRetry: () => void }) {
  return (
    <div className={styles.wrap}>
      <EmptyState title="We can't connect right now" action={<Button onClick={onRetry}>Try again</Button>}>
        Check your internet connection, then try again.
      </EmptyState>
    </div>
  );
}

import { Button } from "./Button";
import { EmptyState } from "./EmptyState";
import styles from "./ConnectionProblem.module.css";

export function ConnectionProblem({ onRetry }: { onRetry: () => void }) {
  return (
    <div className={styles.wrap}>
      <EmptyState title="We can't reach RepoViva right now" action={<Button onClick={onRetry}>Try again</Button>}>
        The server didn't answer. If you're running it locally, check that Core API is up.
      </EmptyState>
    </div>
  );
}

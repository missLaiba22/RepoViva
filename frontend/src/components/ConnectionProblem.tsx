import { ApiError } from "../api/client";
import { Button } from "./Button";
import { EmptyState } from "./EmptyState";
import styles from "./ConnectionProblem.module.css";

export function ConnectionProblem({ error, onRetry }: { error: unknown; onRetry: () => void }) {
  // Status 0 is the only case where the request never reached us.
  const offline = error instanceof ApiError && error.status === 0;
  return (
    <div className={styles.wrap}>
      <EmptyState
        title={offline ? "We can't connect right now" : "Something went wrong on our side"}
        action={<Button onClick={onRetry}>Try again</Button>}
      >
        {offline
          ? "Check your internet connection, then try again."
          : "This is usually temporary. Please try again in a moment."}
      </EmptyState>
    </div>
  );
}

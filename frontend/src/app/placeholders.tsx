import { ButtonLink } from "../components/Button";
import { EmptyState } from "../components/EmptyState";
import styles from "./placeholders.module.css";

/** Routes that exist so the home page's links work, ahead of their screens. */
export function NotBuiltYet({ title }: { title: string }) {
  return (
    <EmptyState title={title} action={<ButtonLink to="/home" variant="secondary">Back to home</ButtonLink>}>
      This screen is coming next.
    </EmptyState>
  );
}

export function NotFound() {
  return (
    <div className={styles.narrow}>
      <EmptyState title="Page not found" action={<ButtonLink to="/home">Go to home</ButtonLink>}>
        This page doesn&rsquo;t exist, or it belongs to another account.
      </EmptyState>
    </div>
  );
}

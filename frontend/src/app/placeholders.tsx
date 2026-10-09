import { ButtonLink } from "../components/Button";
import { EmptyState } from "../components/EmptyState";
import styles from "./placeholders.module.css";

export function NotFound() {
  return (
    <div className={styles.narrow}>
      <EmptyState title="Page not found" action={<ButtonLink to="/home">Go to home</ButtonLink>}>
        This page doesn&rsquo;t exist, or it belongs to another account.
      </EmptyState>
    </div>
  );
}

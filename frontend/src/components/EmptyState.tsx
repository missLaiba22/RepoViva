import type { ReactNode } from "react";
import { Card } from "./Card";
import styles from "./EmptyState.module.css";

export function EmptyState({ title, children, action }: { title: string; children: ReactNode; action?: ReactNode }) {
  return (
    <Card className={styles.empty}>
      <h3 className={styles.title}>{title}</h3>
      <p className={styles.body}>{children}</p>
      {action && <div className={styles.action}>{action}</div>}
    </Card>
  );
}

import type { ReactNode } from "react";
import { Card } from "./Card";
import { Icon, type IconName } from "./Icon";
import styles from "./EmptyState.module.css";

export function EmptyState({
  title,
  children,
  action,
  icon,
  tone = "neutral",
}: {
  title: string;
  children: ReactNode;
  action?: ReactNode;
  icon?: IconName;
  tone?: "neutral" | "warning";
}) {
  return (
    <Card className={styles.empty}>
      {icon && (
        <span className={`${styles.icon} ${styles[tone]}`} aria-hidden="true">
          <Icon name={icon} size={24} />
        </span>
      )}
      <h3 className={styles.title}>{title}</h3>
      <p className={styles.body}>{children}</p>
      {action && <div className={styles.action}>{action}</div>}
    </Card>
  );
}

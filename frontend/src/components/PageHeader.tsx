import type { ReactNode } from "react";
import { Link } from "react-router-dom";
import styles from "./PageHeader.module.css";

export interface Crumb {
  label: ReactNode;
  to: string;
}

/** The same header on every signed-in page: where you are, what this page
 * is, and its main action. */
export function PageHeader({
  crumbs = [],
  title,
  lead,
  actions,
}: {
  crumbs?: Crumb[];
  title: ReactNode;
  lead?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <header className={styles.header}>
      {crumbs.length > 0 && (
        <nav aria-label="Breadcrumb">
          <ol className={styles.crumbs}>
            {crumbs.map((crumb) => (
              <li key={crumb.to}>
                <Link to={crumb.to} className={styles.crumb}>
                  {crumb.label}
                </Link>
              </li>
            ))}
          </ol>
        </nav>
      )}
      <div className={styles.row}>
        <div className={styles.text}>
          <h1 className={styles.title}>{title}</h1>
          {lead && <div className={styles.lead}>{lead}</div>}
        </div>
        {actions && <div className={styles.actions}>{actions}</div>}
      </div>
    </header>
  );
}

import type { ReactNode } from "react";
import type { Interview, Repository } from "../../api/types";
import { ButtonLink } from "../../components/Button";
import { Card } from "../../components/Card";
import { Icon } from "../../components/Icon";
import { repoName } from "../../lib/format";
import { isIndexing } from "./api";
import styles from "./GettingStarted.module.css";

interface Step {
  title: string;
  body: string;
  done: boolean;
  action?: ReactNode;
}

/** First-run guide, worked out from what the user already has, so it needs
 * no stored state and disappears once a first interview has ended. */
export function GettingStarted({
  login,
  repositories,
  interviews,
}: {
  login?: string;
  repositories: Repository[];
  interviews: Interview[];
}) {
  const ready = repositories.find((r) => r.status === "ready");
  const preparing = repositories.find((r) => isIndexing(r.status));
  const interviewed = interviews.some((i) => i.status === "completed" || i.status === "interrupted");

  const steps: Step[] = [
    {
      title: "Connect your first repository",
      body: "Paste a public GitHub link to code you wrote or know well.",
      done: repositories.length > 0,
      action: <ButtonLink to="/repositories/new">Connect repository</ButtonLink>,
    },
    {
      title: "Let RepoViva read the code",
      body: "It indexes the repository and picks the areas to ask about. Usually a few minutes.",
      done: Boolean(ready),
      action: preparing && (
        <ButtonLink to={`/repositories/${preparing.id}`} variant="secondary">
          See progress
        </ButtonLink>
      ),
    },
    {
      title: "Take your first interview",
      body: "Up to 6 spoken questions about your code, up to 30 minutes. Then read your graded report.",
      done: interviewed,
      action: ready && (
        <ButtonLink to={`/repositories/${ready.id}`}>
          Practice on {repoName(ready.github_url).name}
          <Icon name="arrow" size={16} />
        </ButtonLink>
      ),
    },
  ];
  const current = steps.findIndex((s) => !s.done);

  return (
    <Card className={styles.card}>
      <header className={styles.head}>
        <h2 className={styles.title}>{login ? `Welcome, ${login}` : "Welcome to RepoViva"}</h2>
        <p className={styles.lead}>Three steps to your first mock interview.</p>
      </header>
      <ol className={styles.steps}>
        {steps.map((step, index) => {
          const state = step.done ? "done" : index === current ? "current" : "todo";
          return (
            <li key={step.title} className={`${styles.step} ${styles[state]}`}>
              <span className={styles.marker} aria-hidden="true">
                {step.done ? <Icon name="check" size={14} /> : index + 1}
              </span>
              <div className={styles.body}>
                <h3 className={styles.stepTitle}>
                  {step.title}
                  {step.done && <span className="visually-hidden"> (done)</span>}
                </h3>
                {state === "current" && (
                  <>
                    <p className={styles.text}>{step.body}</p>
                    {step.action && <div className={styles.action}>{step.action}</div>}
                  </>
                )}
              </div>
            </li>
          );
        })}
      </ol>
    </Card>
  );
}

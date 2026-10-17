import { Navigate } from "react-router-dom";
import { ButtonAnchor } from "../../components/Button";
import { Icon, type IconName } from "../../components/Icon";
import { Logo } from "../../components/Logo";
import { PageSpinner } from "../../components/Spinner";
import { ThemeToggle } from "../../components/ThemeToggle";
import { SIGN_IN_URL } from "./api";
import { useAuth } from "./authContext";
import styles from "./LandingPage.module.css";

const STEPS: { icon: IconName; label: string }[] = [
  { icon: "repo", label: "Connect a repository" },
  { icon: "mic", label: "Answer out loud" },
  { icon: "report", label: "Review the report" },
];

export function LandingPage() {
  const auth = useAuth();
  if (auth.status === "loading") return <PageSpinner />;
  if (auth.status === "signed-in") return <Navigate to="/repositories" replace />;

  return (
    <div className={styles.page}>
      <header className={styles.top}>
        <Logo />
        <ThemeToggle />
      </header>

      <main className={styles.main}>
        <section className={styles.hero}>
          <h1 className={styles.title}>Practise explaining the code you actually wrote.</h1>
          <p className={styles.lead}>Spoken mock interviews about your own GitHub repository, graded against the code.</p>
          <div className={styles.actions}>
            <ButtonAnchor href={SIGN_IN_URL} size="large">
              <GitHubMark />
              Sign in with GitHub
            </ButtonAnchor>
            <span className={styles.note}>Public repositories</span>
          </div>
          <ol className={styles.steps} aria-label="How it works">
            {STEPS.map((step) => (
              <li key={step.label}>
                <Icon name={step.icon} size={16} />
                {step.label}
              </li>
            ))}
          </ol>
        </section>

        <InterviewPreview />
      </main>
    </div>
  );
}

/** A still of the live interview screen: shows the product instead of describing it. */
function InterviewPreview() {
  return (
    <figure className={styles.preview} aria-label="Preview of a live interview">
      <div className={styles.previewTop}>
        <span className={styles.previewRepo}>acme/checkout-api</span>
        <span className={styles.previewSteps} aria-hidden="true">
          <i className={styles.done} />
          <i className={styles.now} />
          <i />
          <i />
        </span>
      </div>
      <div className={styles.previewBody}>
        <p className={styles.previewCounter}>Question 2 of 4</p>
        <p className={styles.previewQuestion}>
          Why does <code>place_order</code> lock the stock rows in product order?
        </p>
        <div className={styles.previewMic}>
          <span className={styles.previewButton}>
            <Icon name="mic" size={22} />
          </span>
          <span className={styles.previewWave} aria-hidden="true">
            {[40, 70, 55, 90, 60, 35, 75, 50, 30].map((h, i) => (
              <i key={i} style={{ height: `${h}%` }} />
            ))}
          </span>
          <span className={styles.previewLabel}>Listening · 0:42</span>
        </div>
      </div>
    </figure>
  );
}

function GitHubMark() {
  return (
    <svg width="18" height="18" viewBox="0 0 16 16" aria-hidden="true" fill="currentColor">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
    </svg>
  );
}

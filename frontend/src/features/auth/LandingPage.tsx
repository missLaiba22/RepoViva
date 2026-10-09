import { Navigate } from "react-router-dom";
import { ButtonAnchor } from "../../components/Button";
import { Logo } from "../../components/Logo";
import { PageSpinner } from "../../components/Spinner";
import { ThemeToggle } from "../../components/ThemeToggle";
import { SIGN_IN_URL } from "./api";
import { useAuth } from "./authContext";
import styles from "./LandingPage.module.css";

const STEPS = [
  {
    title: "Connect a repository",
    body: "Paste a GitHub link. RepoViva reads and indexes the code, usually in a few minutes.",
  },
  {
    title: "Talk it through",
    body: "Answer six spoken questions about how your project works, with follow-ups on what you say.",
  },
  {
    title: "Learn from the report",
    body: "Each answer is checked against your code, with the points a strong answer covers and the files to revisit.",
  },
];

export function LandingPage() {
  const auth = useAuth();
  if (auth.status === "loading") return <PageSpinner />;
  if (auth.status === "signed-in") return <Navigate to="/home" replace />;

  return (
    <div className={styles.page}>
      <header className={styles.top}>
        <Logo />
        <ThemeToggle />
      </header>

      <main>
        <section className={styles.hero}>
          <p className={styles.eyebrow}>Mock interviews about your own code</p>
          <h1 className={styles.title}>Practise explaining the code you actually wrote.</h1>
          <p className={styles.lead}>
            RepoViva studies your repository, interviews you about it out loud, and shows you where your explanation
            matched the code and where it didn&rsquo;t.
          </p>
          <div className={styles.actions}>
            <ButtonAnchor href={SIGN_IN_URL} size="large">
              <GitHubMark />
              Sign in with GitHub
            </ButtonAnchor>
            <span className={styles.note}>Public repositories only, for now.</span>
          </div>
        </section>

        <ol className={styles.steps} aria-label="How it works">
          {STEPS.map((step) => (
            <li key={step.title} className={styles.step}>
              <h2 className={styles.stepTitle}>{step.title}</h2>
              <p className={styles.stepBody}>{step.body}</p>
            </li>
          ))}
        </ol>
      </main>

      <footer className={styles.footer}>RepoViva · interview practice for developers</footer>
    </div>
  );
}

function GitHubMark() {
  return (
    <svg width="18" height="18" viewBox="0 0 16 16" aria-hidden="true" fill="currentColor">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
    </svg>
  );
}

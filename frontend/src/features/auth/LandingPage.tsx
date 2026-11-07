import { Navigate } from "react-router-dom";
import { ButtonAnchor } from "../../components/Button";
import { Icon, type IconName } from "../../components/Icon";
import { Logo } from "../../components/Logo";
import { PageSpinner } from "../../components/Spinner";
import { ThemeToggle } from "../../components/ThemeToggle";
import { SIGN_IN_URL } from "./api";
import { useAuth } from "./authContext";
import styles from "./LandingPage.module.css";

const STEPS: { icon: IconName; title: string; body: string }[] = [
  { icon: "repo", title: "Connect a repo", body: "Paste a public GitHub link" },
  { icon: "folder", title: "We read the code", body: "Up to 6 areas to ask about" },
  { icon: "mic", title: "Answer out loud", body: "Or type, up to 30 min" },
  { icon: "report", title: "Get your report", body: "Graded against the code" },
];

export function LandingPage() {
  const auth = useAuth();
  if (auth.status === "loading") return <PageSpinner />;
  if (auth.status === "signed-in") return <Navigate to="/repositories" replace />;

  return (
    <div className={styles.page}>
      <header className={styles.top}>
        <Logo />
        <nav className={styles.nav} aria-label="Sections">
          <a href="#how">How it works</a>
          <a href="#report">Sample report</a>
        </nav>
        <ThemeToggle />
      </header>

      <main>
        <section className={`${styles.wrap} ${styles.hero}`}>
          <div>
            <h1 className={styles.title}>Practise explaining the code you actually wrote.</h1>
            <p className={styles.lead}>Spoken mock interviews about your own repository, graded against the code.</p>
            <div className={styles.actions}>
              <ButtonAnchor href={SIGN_IN_URL} size="large">
                <GitHubMark />
                Sign in with GitHub
              </ButtonAnchor>
              <a href="#report" className={styles.secondary}>
                See a sample report
                <Icon name="arrow" size={16} />
              </a>
            </div>
            <ul className={styles.badges} aria-label="Good to know">
              <li>
                <Icon name="repo" size={14} />
                Public repositories
              </li>
              <li>
                <Icon name="check" size={14} />
                Sign-in reads your profile only
              </li>
              <li>
                <Icon name="stop" size={14} />
                Recordings never kept
              </li>
            </ul>
          </div>

          <InterviewPreview />
        </section>

        <section id="how" className={styles.band} aria-labelledby="how-heading">
          <div className={styles.wrap}>
            <SectionHead id="how-heading" kicker="How it works" title="Four steps, one repository" />
            <ol className={styles.steps}>
              {STEPS.map((step) => (
                <li key={step.title} className={styles.step}>
                  <span className={styles.stepIcon} aria-hidden="true">
                    <Icon name={step.icon} size={22} />
                  </span>
                  <h3 className={styles.stepTitle}>{step.title}</h3>
                  <p className={styles.muted}>{step.body}</p>
                </li>
              ))}
            </ol>
          </div>
        </section>

        <section id="report" className={styles.wrap} aria-labelledby="report-heading">
          <div className={styles.split}>
            <div>
              <SectionHead id="report-heading" kicker="What you get" title="Feedback tied to your code" />
              <ul className={styles.checks}>
                <li>A score for each answer</li>
                <li>What you got right, and what you missed</li>
                <li>Links to the exact lines of code</li>
              </ul>
            </div>
            <ReportPreview />
          </div>
        </section>

        <section className={styles.final} aria-labelledby="final-heading">
          <h2 id="final-heading" className={styles.finalTitle}>
            Ready to explain your code?
          </h2>
          <ButtonAnchor href={SIGN_IN_URL} size="large">
            <GitHubMark />
            Get started with GitHub
          </ButtonAnchor>
        </section>
      </main>

      <footer className={`${styles.wrap} ${styles.footer}`}>
        <Logo />
      </footer>
    </div>
  );
}

function SectionHead({ id, kicker, title }: { id: string; kicker: string; title: string }) {
  return (
    <div className={styles.sectionHead}>
      <p className={styles.kicker}>{kicker}</p>
      <h2 id={id} className={styles.sectionTitle}>
        {title}
      </h2>
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
        <p className={styles.previewCounter}>
          Question 2 of 4 · <span className={styles.previewArea}>src/orders/</span>
        </p>
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

/** A still of one graded answer, the shape a real report takes. */
function ReportPreview() {
  return (
    <figure className={styles.report} aria-label="Example of a graded answer">
      <div className={styles.reportHead}>
        <span className={styles.reportLabel}>Question 2 · src/orders/</span>
        <div className={styles.scores}>
          <Score label="Correctness" value={4} />
          <Score label="Clarity" value={3} />
        </div>
      </div>
      <p className={styles.reportQuestion}>Why does place_order lock the stock rows in product order?</p>
      <div className={styles.points}>
        <div>
          <p className={`${styles.pointsTitle} ${styles.good}`}>Strength</p>
          <p>Fixed lock order prevents deadlocks</p>
        </div>
        <div>
          <p className={`${styles.pointsTitle} ${styles.gap}`}>Gap</p>
          <p>Didn&rsquo;t say when the lock is released</p>
        </div>
      </div>
      <span className={styles.cite}>
        <Icon name="file" size={12} />
        orders/service.py:42–67
      </span>
    </figure>
  );
}

function Score({ label, value }: { label: string; value: number }) {
  return (
    <span className={styles.score}>
      {label}
      <strong>{value}/5</strong>
    </span>
  );
}

function GitHubMark() {
  return (
    <svg width="18" height="18" viewBox="0 0 16 16" aria-hidden="true" fill="currentColor">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0016 8c0-4.42-3.58-8-8-8z" />
    </svg>
  );
}

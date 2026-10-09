import { useId, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { ApiError } from "../../api/client";
import { Button, ButtonLink } from "../../components/Button";
import { Card } from "../../components/Card";
import { connectRepository } from "./api";
import { normalizeGithubUrl } from "./githubUrl";
import styles from "./ConnectRepositoryPage.module.css";

const INVALID = "That doesn't look like a GitHub repository. Paste a link like https://github.com/owner/repo.";

export function ConnectRepositoryPage() {
  const navigate = useNavigate();
  const inputId = useId();
  const hintId = useId();
  const [value, setValue] = useState("");
  const [touched, setTouched] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [serverError, setServerError] = useState<string | null>(null);

  const normalized = normalizeGithubUrl(value);
  const showInvalid = touched && value.trim() !== "" && !normalized;
  const error = serverError ?? (showInvalid ? INVALID : null);
  const willUse = normalized && normalized !== value.trim() ? normalized : null;

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setTouched(true);
    setServerError(null);
    if (!normalized) {
      if (value.trim() === "") setServerError("Paste the link to a GitHub repository.");
      return;
    }
    setSubmitting(true);
    try {
      const result = await connectRepository(normalized);
      navigate(`/repositories/${result.repository.id}`, {
        state: { alreadyConnected: result.kind === "existing" },
      });
    } catch (err) {
      setServerError(messageFor(err));
      setSubmitting(false);
    }
  }

  return (
    <div className={styles.page}>
      <header>
        <h1 className={styles.title}>Connect a repository</h1>
        <p className={styles.lead}>RepoViva reads the code so every interview question is about your project.</p>
      </header>

      <Card className={styles.card}>
        <form onSubmit={handleSubmit} noValidate>
          <label htmlFor={inputId} className={styles.label}>
            GitHub repository
          </label>
          <input
            id={inputId}
            className={styles.input}
            type="url"
            inputMode="url"
            autoComplete="off"
            autoCapitalize="off"
            spellCheck={false}
            placeholder="https://github.com/owner/repo"
            value={value}
            onChange={(e) => {
              setValue(e.target.value);
              setServerError(null);
            }}
            onBlur={() => setTouched(true)}
            aria-invalid={error ? true : undefined}
            aria-describedby={hintId}
            autoFocus
          />
          <p id={hintId} className={error ? styles.error : styles.hint} role={error ? "alert" : undefined}>
            {error ??
              (willUse ? (
                <>
                  We&rsquo;ll connect <code>{willUse}</code>
                </>
              ) : (
                "Public repositories only, for now."
              ))}
          </p>

          <div className={styles.actions}>
            <Button type="submit" disabled={submitting}>
              {submitting ? "Connecting…" : "Connect repository"}
            </Button>
            <ButtonLink to="/home" variant="ghost">
              Cancel
            </ButtonLink>
          </div>
        </form>
      </Card>

      <section className={styles.next} aria-labelledby="next-heading">
        <h2 id="next-heading" className={styles.nextTitle}>
          What happens next
        </h2>
        <ol className={styles.steps}>
          <li>RepoViva clones the repository&rsquo;s default branch.</li>
          <li>It splits the code into pieces and indexes them, so questions can quote the right files.</li>
          <li>Usually a few minutes. You can leave the page while it works.</li>
        </ol>
      </section>
    </div>
  );
}

function messageFor(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 422) return INVALID;
    if (error.status === 0) return error.message;
  }
  return "Something went wrong connecting the repository. Please try again.";
}

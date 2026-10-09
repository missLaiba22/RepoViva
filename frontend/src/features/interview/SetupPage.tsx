import { useCallback, useId, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { ApiError } from "../../api/client";
import type { Repository } from "../../api/types";
import { Button, ButtonLink } from "../../components/Button";
import { Card } from "../../components/Card";
import { ConnectionProblem } from "../../components/ConnectionProblem";
import { EmptyState } from "../../components/EmptyState";
import { PageSpinner, Spinner } from "../../components/Spinner";
import { useResource } from "../../hooks/useResource";
import { repoName } from "../../lib/format";
import { getRepository } from "../repositories";
import { micSupported, playTestSound, type MicErrorKind } from "./audio/microphone";
import { createInterview, type AnswerMode, type LiveHandoff } from "./api";
import { LevelMeter } from "./LevelMeter";
import { useMicCheck } from "./useMicCheck";
import styles from "./SetupPage.module.css";

export function SetupPage() {
  const id = Number(useParams().id);
  const load = useCallback(() => getRepository(id), [id]);
  const repo = useResource(load);

  if (repo.state === "loading") return <PageSpinner />;
  if (repo.state === "error") {
    if (repo.error instanceof ApiError && (repo.error.status === 404 || repo.error.status === 422)) {
      return (
        <EmptyState title="Repository not found" action={<ButtonLink to="/home">Back to home</ButtonLink>}>
          It may have been removed, or it belongs to another account.
        </EmptyState>
      );
    }
    return <ConnectionProblem onRetry={repo.reload} />;
  }
  if (repo.data.status !== "ready") {
    return (
      <EmptyState
        title="This repository isn't ready yet"
        action={<ButtonLink to={`/repositories/${id}`}>See its status</ButtonLink>}
      >
        Interviews start once indexing has finished.
      </EmptyState>
    );
  }
  return <Setup repository={repo.data} />;
}

function Setup({ repository }: { repository: Repository }) {
  const navigate = useNavigate();
  const { check, start, stop } = useMicCheck();
  const [mode, setMode] = useState<AnswerMode>(micSupported() ? "voice" : "text");
  const [starting, setStarting] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const typeId = useId();
  const { owner, name } = repoName(repository.github_url);

  const micReady = check.state === "live" && check.heard;
  const canStart = (mode === "text" || micReady) && !starting;

  async function handleStart() {
    setStarting(true);
    setStartError(null);
    const deviceId = check.state === "live" ? check.deviceId : undefined;
    try {
      const interview = await createInterview(repository.id);
      stop(); // The live page opens its own microphone.
      const handoff: LiveHandoff = {
        interviewId: interview.id,
        token: interview.session_token,
        tokenExpiresAt: interview.session_token_expires_at,
        repositoryId: repository.id,
        repositoryName: name,
        mode,
        deviceId,
      };
      navigate(`/interviews/${interview.id}/live`, { state: handoff, replace: true });
    } catch (error) {
      setStartError(
        error instanceof ApiError && error.status === 409
          ? "This repository is no longer ready for an interview. Check its status and try again."
          : "We couldn't start the interview. Please try again.",
      );
      setStarting(false);
    }
  }

  return (
    <div className={styles.page}>
      <Link to={`/repositories/${repository.id}`} className={styles.back}>
        ← {name}
      </Link>

      <header>
        <h1 className={styles.title}>Before you start</h1>
        <p className={styles.lead}>
          An interview about{" "}
          <span className={styles.repo}>
            {owner && <span className={styles.owner}>{owner}/</span>}
            {name}
          </span>
          . Find a quiet spot; it takes about 15 minutes.
        </p>
      </header>

      <ol className={styles.expect} aria-label="What to expect">
        <li>
          <strong>Six questions about how your project works,</strong> asked out loud and shown on screen. Each
          one follows up on what you said before.
        </li>
        <li>
          <strong>Tap the microphone to answer, and tap again when you&rsquo;re done.</strong> There&rsquo;s no
          rush: pauses are fine, up to 3 minutes per answer.
        </li>
        <li>
          <strong>Stop whenever you like.</strong> You still get a report on the questions you answered.
        </li>
      </ol>

      <Card className={styles.card}>
        <div className={styles.cardHead}>
          <h2 className={styles.cardTitle}>Microphone</h2>
          {mode === "voice" && micReady && <span className={styles.ok}>✓ We can hear you</span>}
        </div>

        {mode === "text" ? (
          <p className={styles.muted}>You&rsquo;ll type your answers. The questions are still read aloud.</p>
        ) : (
          <MicPanel check={check} onStart={start} />
        )}

        {micSupported() && (
          <label htmlFor={typeId} className={styles.toggle}>
            <input
              id={typeId}
              type="checkbox"
              checked={mode === "text"}
              onChange={(e) => {
                const next = e.target.checked ? "text" : "voice";
                setMode(next);
                if (next === "text") stop();
              }}
            />
            Type my answers instead of speaking
          </label>
        )}
      </Card>

      <Card className={styles.card}>
        <div className={styles.cardHead}>
          <h2 className={styles.cardTitle}>Speakers</h2>
        </div>
        <SpeakerPanel />
      </Card>

      <div className={styles.footer}>
        {startError && (
          <p className={styles.error} role="alert">
            {startError}
          </p>
        )}
        <div className={styles.startRow}>
          <Button size="large" onClick={handleStart} disabled={!canStart}>
            {starting ? "Starting…" : "Start interview"}
          </Button>
          {!canStart && !starting && (
            <span className={styles.muted}>
              {check.state === "live" ? "Say a few words to check your microphone." : "Check your microphone first."}
            </span>
          )}
        </div>
        <p className={styles.privacy}>
          Your answers are transcribed to text for grading. The audio itself is never stored.
        </p>
      </div>
    </div>
  );
}

const MIC_ERRORS: Record<MicErrorKind, { title: string; body: string }> = {
  denied: {
    title: "Microphone access is blocked",
    body: "Allow the microphone for this site from the icon in your browser's address bar, then try again.",
  },
  "not-found": {
    title: "No microphone found",
    body: "Plug in a microphone or headset, then try again.",
  },
  busy: {
    title: "Your microphone is in use",
    body: "Another app may be using it. Close it, then try again.",
  },
  unsupported: {
    title: "This browser can't use a microphone here",
    body: "Try a recent Chrome, Edge, Firefox or Safari, or type your answers instead.",
  },
};

function MicPanel({ check, onStart }: { check: ReturnType<typeof useMicCheck>["check"]; onStart: (deviceId?: string) => void }) {
  const selectId = useId();

  if (check.state === "idle") {
    return (
      <div className={styles.panel}>
        <p className={styles.muted}>RepoViva needs your microphone to hear your answers.</p>
        <div>
          <Button onClick={() => onStart()}>Check my microphone</Button>
        </div>
      </div>
    );
  }

  if (check.state === "requesting") {
    return (
      <p className={styles.waiting}>
        <Spinner label="Waiting for permission" /> Waiting for you to allow the microphone…
      </p>
    );
  }

  if (check.state === "error") {
    const { title, body } = MIC_ERRORS[check.kind];
    return (
      <div className={styles.panel} role="alert">
        <p className={styles.problemTitle}>{title}</p>
        <p className={styles.muted}>{body}</p>
        <div>
          <Button variant="secondary" onClick={() => onStart()}>
            Try again
          </Button>
        </div>
      </div>
    );
  }

  return (
    <div className={styles.panel}>
      {check.devices.length > 1 && (
        <div className={styles.field}>
          <label htmlFor={selectId} className={styles.fieldLabel}>
            Input
          </label>
          <select
            id={selectId}
            className={styles.select}
            value={check.deviceId}
            onChange={(e) => onStart(e.target.value)}
          >
            {check.devices.map((d, i) => (
              <option key={d.deviceId} value={d.deviceId}>
                {d.label || `Microphone ${i + 1}`}
              </option>
            ))}
          </select>
        </div>
      )}
      <LevelMeter level={check.level} />
      <p className={styles.muted} aria-live="polite">
        {check.heard ? "Sounds good. You're ready." : "Say a few words, as if you were answering a question."}
      </p>
    </div>
  );
}

function SpeakerPanel() {
  const [playing, setPlaying] = useState(false);

  async function handlePlay() {
    setPlaying(true);
    try {
      await playTestSound();
    } finally {
      setPlaying(false);
    }
  }

  return (
    <div className={styles.panel}>
      <p className={styles.muted}>Questions are spoken aloud. Make sure you can hear this at a comfortable volume.</p>
      <div>
        <Button variant="secondary" onClick={handlePlay} disabled={playing}>
          {playing ? "Playing…" : "Play test sound"}
        </Button>
      </div>
    </div>
  );
}

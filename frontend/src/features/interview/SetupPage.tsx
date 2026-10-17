import { useCallback, useId, useState, type ReactNode } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ApiError } from "../../api/client";
import type { Repository } from "../../api/types";
import { Button, ButtonLink } from "../../components/Button";
import { Card } from "../../components/Card";
import { ConnectionProblem } from "../../components/ConnectionProblem";
import { EmptyState } from "../../components/EmptyState";
import { Facts } from "../../components/Facts";
import { Icon } from "../../components/Icon";
import { PageHeader } from "../../components/PageHeader";
import { RepoName } from "../../components/RepoName";
import { PageSpinner, Spinner } from "../../components/Spinner";
import { useResource } from "../../hooks/useResource";
import { REPOSITORIES_CRUMB } from "../../lib/crumbs";
import { INTERVIEW_FACTS } from "../../lib/interviewFacts";
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
        <EmptyState title="Repository not found" action={<ButtonLink to="/repositories">Back to repositories</ButtonLink>}>
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
        action={<ButtonLink to={`/repositories/${id}`}>See progress</ButtonLink>}
      >
        ItInterviews open once we&rsquo;ve finished reading your code, usually within a few minutes.rsquo;s still being prepared, usually for a few minutes.
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
  const { name } = repoName(repository.github_url);

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
      <PageHeader
        crumbs={[REPOSITORIES_CRUMB, { label: name, to: `/repositories/${repository.id}` }]}
        title="Before you start"
        lead={<RepoName githubUrl={repository.github_url} />}
      />

      <Facts items={INTERVIEW_FACTS} label="What to expect" />

      <Card className={styles.card}>
        <div className={styles.row}>
          <span className={styles.rowIcon}>
            <Icon name="mic" />
          </span>
          {mode === "text" ? (
            <div className={styles.rowMain}>
              <h2 className={styles.rowTitle}>Microphone</h2>
              <p className={styles.muted}>Off. You&rsquo;ll type your answers.</p>
            </div>
          ) : (
            <MicPanel check={check} onStart={start} />
          )}
        </div>

        <div className={styles.row}>
          <span className={styles.rowIcon}>
            <Icon name="speaker" />
          </span>
          <SpeakerPanel />
        </div>

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
        <p className={styles.privacy}>Answers are transcribed for your report. Recordings are never kept.</p>
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
      <RowBody title="Microphone" hint="Needed to hear your answers.">
        <Button variant="secondary" onClick={() => onStart()}>
          Check my microphone
        </Button>
      </RowBody>
    );
  }

  if (check.state === "requesting") {
    return (
      <RowBody
        title="Microphone"
        hint={
          <span className={styles.waiting}>
            <Spinner label="Waiting for permission" /> Allow the microphone in your browser…
          </span>
        }
      />
    );
  }

  if (check.state === "error") {
    const { title, body } = MIC_ERRORS[check.kind];
    return (
      <div className={styles.rowMain} role="alert">
        <div className={styles.rowHead}>
          <div>
            <h2 className={styles.rowTitle}>Microphone</h2>
            <p className={styles.problemTitle}>{title}</p>
          </div>
          <Button variant="secondary" onClick={() => onStart()}>
            Try again
          </Button>
        </div>
        <p className={styles.muted}>{body}</p>
      </div>
    );
  }

  return (
    <div className={styles.rowMain}>
      <div className={styles.rowHead}>
        <div>
          <h2 className={styles.rowTitle}>Microphone</h2>
          <p className={check.heard ? styles.ok : styles.muted} aria-live="polite">
            {check.heard ? (
              <>
                <Icon name="check" size={14} /> We can hear you
              </>
            ) : (
              "Say a few words, as if answering."
            )}
          </p>
        </div>
      </div>
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
    <RowBody title="Speakers" hint="Questions are read aloud.">
      <Button variant="secondary" onClick={handlePlay} disabled={playing}>
        <Icon name="play" size={14} />
        {playing ? "Playing…" : "Play test sound"}
      </Button>
    </RowBody>
  );
}

function RowBody({ title, hint, children }: { title: string; hint: ReactNode; children?: ReactNode }) {
  return (
    <div className={styles.rowMain}>
      <div className={styles.rowHead}>
        <div>
          <h2 className={styles.rowTitle}>{title}</h2>
          <p className={styles.muted}>{hint}</p>
        </div>
        {children}
      </div>
    </div>
  );
}

import { useCallback, useId, useState, type ReactNode } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { ApiError } from "../../api/client";
import type { Repository } from "../../api/types";
import { Button, ButtonLink } from "../../components/Button";
import { Card } from "../../components/Card";
import { ConnectionProblem } from "../../components/ConnectionProblem";
import { EmptyState } from "../../components/EmptyState";
import { Facts } from "../../components/Facts";
import { Icon, type IconName } from "../../components/Icon";
import { PageHeader } from "../../components/PageHeader";
import { RepoName } from "../../components/RepoName";
import { PageSpinner } from "../../components/Spinner";
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
        Interviews open once we&rsquo;ve finished reading your code, usually within a few minutes.
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
        <header className={styles.cardHead}>
          <h2 className={styles.cardTitle}>Audio check</h2>
          <p className={styles.muted}>Takes a few seconds. Check both before you begin.</p>
        </header>

        {mode === "text" ? (
          <Row
            icon="mic"
            title="Microphone"
            status={<Status tone="neutral">Off</Status>}
            hint={<>You&rsquo;ll type your answers.</>}
          />
        ) : (
          <MicRow check={check} onStart={start} />
        )}

        <SpeakerRow />

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
            <Icon name="alert" size={16} />
            {startError}
          </p>
        )}
        <div className={styles.startRow}>
          <Button size="large" onClick={handleStart} disabled={!canStart}>
            {starting ? "Starting…" : "Start interview"}
          </Button>
          {!canStart && !starting && (
            <span className={styles.muted}>
              {check.state === "live"
                ? "Say a few words to finish the microphone check."
                : "Check your microphone to continue."}
            </span>
          )}
        </div>
        <p className={styles.privacy}>Answers are transcribed for your report. Recordings are never kept.</p>
      </div>
    </div>
  );
}

const MIC_ERRORS: Record<MicErrorKind, { status: string; title: string; body: string }> = {
  denied: {
    status: "Blocked",
    title: "Microphone access is blocked",
    body: "Allow the microphone for this site from the icon in your browser's address bar, then try again.",
  },
  "not-found": {
    status: "Not found",
    title: "No microphone found",
    body: "Plug in a microphone or headset, then try again.",
  },
  busy: {
    status: "In use",
    title: "Your microphone is in use",
    body: "Another app may be using it. Close it, then try again.",
  },
  unsupported: {
    status: "Not supported",
    title: "This browser can't use a microphone here",
    body: "Try a recent Chrome, Edge, Firefox or Safari, or type your answers instead.",
  },
};

function MicRow({ check, onStart }: { check: ReturnType<typeof useMicCheck>["check"]; onStart: (deviceId?: string) => void }) {
  const selectId = useId();

  if (check.state === "idle") {
    return (
      <Row
        icon="mic"
        title="Microphone"
        status={<Status tone="neutral">Not checked</Status>}
        hint="Needed to hear your answers."
        action={
          <Button variant="secondary" onClick={() => onStart()}>
            Check my microphone
          </Button>
        }
      />
    );
  }

  if (check.state === "requesting") {
    return (
      <Row
        icon="mic"
        title="Microphone"
        status={<Status tone="progress">Waiting for permission</Status>}
        hint={<>Allow the microphone in your browser&rsquo;s prompt.</>}
      />
    );
  }

  if (check.state === "error") {
    const { status, title, body } = MIC_ERRORS[check.kind];
    return (
      <Row
        icon="mic"
        title="Microphone"
        status={<Status tone="error">{status}</Status>}
        hint={
          <>
            <span className={styles.problemTitle}>{title}.</span> {body}
          </>
        }
        action={
          <Button variant="secondary" onClick={() => onStart()}>
            Try again
          </Button>
        }
        alert
      />
    );
  }

  return (
    <Row
      icon="mic"
      title="Microphone"
      status={check.heard ? <Status tone="ok">Working</Status> : <Status tone="progress">Listening</Status>}
      hint={check.heard ? "We can hear you clearly." : "Say a few words, as if answering a question."}
    >
      <LevelMeter level={check.level} />
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
    </Row>
  );
}

function SpeakerRow() {
  const [state, setState] = useState<"idle" | "playing" | "played">("idle");

  async function handlePlay() {
    setState("playing");
    try {
      await playTestSound();
    } finally {
      setState("played");
    }
  }

  const status =
    state === "idle" ? (
      <Status tone="neutral">Not tested</Status>
    ) : state === "playing" ? (
      <Status tone="progress">Playing</Status>
    ) : (
      <Status tone="ok">Tested</Status>
    );

  return (
    <Row
      icon="speaker"
      title="Speakers"
      status={status}
      hint={state === "played" ? <>Didn&rsquo;t hear it? Check your volume and output device.</> : "Questions are read aloud."}
      action={
        <Button variant="secondary" onClick={handlePlay} disabled={state === "playing"}>
          <Icon name={state === "played" ? "replay" : "play"} size={14} />
          {state === "played" ? "Play again" : "Play test sound"}
        </Button>
      }
    />
  );
}

function Row({
  icon,
  title,
  status,
  hint,
  action,
  alert = false,
  children,
}: {
  icon: IconName;
  title: string;
  status: ReactNode;
  hint: ReactNode;
  action?: ReactNode;
  alert?: boolean;
  children?: ReactNode;
}) {
  return (
    <section className={styles.row} aria-label={title} role={alert ? "alert" : undefined}>
      <span className={styles.rowIcon} aria-hidden="true">
        <Icon name={icon} size={18} />
      </span>
      <div className={styles.rowMain}>
        <div className={styles.rowHead}>
          <div className={styles.rowText}>
            <div className={styles.rowTitleLine}>
              <h3 className={styles.rowTitle}>{title}</h3>
              <span aria-live="polite">{status}</span>
            </div>
            <p className={styles.hint}>{hint}</p>
          </div>
          {action}
        </div>
        {children}
      </div>
    </section>
  );
}

const TONES = {
  neutral: styles.toneNeutral,
  progress: styles.toneProgress,
  ok: styles.toneOk,
  error: styles.toneError,
};

function Status({ tone, children }: { tone: keyof typeof TONES; children: ReactNode }) {
  return <span className={`${styles.status} ${TONES[tone]}`}>{children}</span>;
}

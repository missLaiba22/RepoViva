import { useCallback, useEffect, useId, useState, type FormEvent } from "react";
import { useBlocker, useLocation, useParams } from "react-router-dom";
import type { Plan } from "../../../api/types";
import { Button, ButtonLink } from "../../../components/Button";
import { ConnectionProblem } from "../../../components/ConnectionProblem";
import { Spinner } from "../../../components/Spinner";
import { usePolling } from "../../../hooks/usePolling";
import { useResource } from "../../../hooks/useResource";
import { getPlan, retryPlan, type LiveHandoff } from "../api";
import { LevelMeter } from "../LevelMeter";
import { MicButton } from "./MicButton";
import { MAX_ANSWER_SECONDS, MAX_TEXT_ANSWER, QUESTIONS_PER_INTERVIEW } from "./protocol";
import { useLiveInterview, type LiveInterview } from "./useLiveInterview";
import { useLevel } from "./useLevel";
import styles from "./LivePage.module.css";

/** The live interview: a focused room with the question, the mic and little else. */
export function LivePage() {
  const id = Number(useParams().id);
  const handoff = useLocation().state as LiveHandoff | null;

  // The token only ever lives in router state, so a reload or a pasted
  // link can't rejoin. That's by design (decision 035).
  if (!handoff || handoff.interviewId !== id) return <CannotResume interviewId={id} />;
  return <PlanGate handoff={handoff} />;
}

const PLAN_POLL_MS = 2000;

/** Opens the session only once the questions are written: Voice Service
 * ends a session that starts earlier (decision 052). */
function PlanGate({ handoff }: { handoff: LiveHandoff }) {
  const load = useCallback(() => getPlan(handoff.interviewId), [handoff.interviewId]);
  const plan = useResource(load);
  const generating = plan.state === "loading" || (plan.state === "ready" && plan.data.plan_status === "generating");
  usePolling(plan.reload, PLAN_POLL_MS, plan.state === "ready" && generating);

  if (plan.state === "error") return <ConnectionProblem onRetry={plan.reload} />;
  if (plan.state === "ready" && plan.data.plan_status === "ready") return <Live handoff={handoff} />;
  if (plan.state === "ready" && plan.data.plan_status === "failed") {
    return <PlanFailed handoff={handoff} retryable={plan.data.retryable === true} onRetried={plan.set} />;
  }
  return (
    <div className={styles.endScreen}>
      <Waiting text="Preparing your interview…" />
      <p className={styles.endText}>We&rsquo;re reading your code and writing your questions. This takes a few seconds.</p>
    </div>
  );
}

function PlanFailed({
  handoff,
  retryable,
  onRetried,
}: {
  handoff: LiveHandoff;
  retryable: boolean;
  onRetried: (plan: Plan) => void;
}) {
  const [retrying, setRetrying] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleRetry() {
    setRetrying(true);
    setError(null);
    try {
      onRetried(await retryPlan(handoff.interviewId));
    } catch {
      setError("Interview preparation is unavailable right now. Please try again in a little while.");
      setRetrying(false);
    }
  }

  return (
    <div className={styles.endScreen}>
      <h1 className={styles.endTitle}>We couldn&rsquo;t prepare your interview</h1>
      <p className={styles.endText}>
        {retryable
          ? "Writing the questions failed, most often because the question service is busy. Your code is fine, so it can simply run again."
          : "We found no code in this repository to ask about."}
      </p>
      {error && (
        <p className={styles.notice} role="alert">
          {error}
        </p>
      )}
      <div className={styles.endActions}>
        {retryable && (
          <Button onClick={handleRetry} disabled={retrying} size="large">
            {retrying ? "Starting…" : "Try again"}
          </Button>
        )}
        <ButtonLink to={`/repositories/${handoff.repositoryId}`} variant={retryable ? "ghost" : "primary"}>
          Back to the repository
        </ButtonLink>
      </div>
    </div>
  );
}

const ACTIVE = new Set(["connecting", "preparing", "asking", "answering", "recording", "sending"]);

function Live({ handoff }: { handoff: LiveHandoff }) {
  const live = useLiveInterview(handoff);
  const { state } = live;
  const [confirmingEnd, setConfirmingEnd] = useState(false);
  const active = ACTIVE.has(state.phase);

  // Leaving mid-interview ends it: ask first, inside the app and on tab close.
  const blocker = useBlocker(({ currentLocation, nextLocation }) => active && currentLocation.pathname !== nextLocation.pathname);
  useEffect(() => {
    if (!active) return;
    const warn = (event: BeforeUnloadEvent) => event.preventDefault();
    window.addEventListener("beforeunload", warn);
    return () => window.removeEventListener("beforeunload", warn);
  }, [active]);

  if (state.phase === "done") return <Finished handoff={handoff} answered={state.answered} outcome={state.outcome} />;
  if (state.phase === "failed") return <Failed handoff={handoff} answered={state.answered} rejected={state.failure === "rejected"} />;

  const showConfirm = confirmingEnd || blocker.state === "blocked";
  const questionNumber = Math.max(1, state.seq);

  return (
    <div className={styles.room}>
      <header className={styles.top}>
        <span className={styles.repo}>{handoff.repositoryName}</span>
        <Progress current={state.seq} answered={state.answered} />
        {state.phase !== "ending" && (
          <Button variant="ghost" onClick={() => setConfirmingEnd(true)}>
            End interview
          </Button>
        )}
      </header>

      <main className={styles.stage}>
        {state.phase === "connecting" ? (
          <Waiting text="Connecting to your interviewer…" />
        ) : state.question === null ? (
          <Waiting text="Reading your code and preparing the first question…" />
        ) : (
          <>
            <p className={styles.counter}>
              Question {questionNumber} of {QUESTIONS_PER_INTERVIEW}
            </p>
            <h1 className={styles.question} aria-live="polite">
              {state.question}
            </h1>
            <QuestionAudio live={live} />
            <AnswerArea live={live} />
          </>
        )}
      </main>

      {showConfirm && (
        <div className={styles.confirm} role="dialog" aria-labelledby="end-title">
          <div className={styles.confirmBody}>
            <p id="end-title" className={styles.confirmTitle}>
              End the interview now?
            </p>
            <p className={styles.confirmText}>You&rsquo;ll get a report on the questions you&rsquo;ve answered.</p>
          </div>
          <div className={styles.confirmActions}>
            <Button
              onClick={() => {
                setConfirmingEnd(false);
                if (blocker.state === "blocked") blocker.proceed();
                else live.end();
              }}
            >
              End interview
            </Button>
            <Button
              variant="secondary"
              onClick={() => {
                setConfirmingEnd(false);
                if (blocker.state === "blocked") blocker.reset();
              }}
            >
              Keep going
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}

function Progress({ current, answered }: { current: number; answered: number }) {
  return (
    <ol className={styles.progress} aria-label={`${answered} of ${QUESTIONS_PER_INTERVIEW} answered`}>
      {Array.from({ length: QUESTIONS_PER_INTERVIEW }, (_, i) => {
        const n = i + 1;
        const tone = n <= answered ? styles.stepDone : n === current ? styles.stepNow : styles.stepLater;
        return <li key={n} className={tone} />;
      })}
    </ol>
  );
}

function Waiting({ text }: { text: string }) {
  return (
    <div className={styles.waiting} role="status">
      <Spinner label={text} />
      <p>{text}</p>
    </div>
  );
}

function QuestionAudio({ live }: { live: LiveInterview }) {
  const { state } = live;
  if (live.audioBlocked) {
    return (
      <div className={styles.audioRow}>
        <Button onClick={live.unblockAudio}>▶ Play the question</Button>
        <span className={styles.muted}>Your browser needs a tap before it plays sound.</span>
      </div>
    );
  }
  if (state.phase === "asking") {
    return (
      <div className={styles.audioRow}>
        <span className={styles.speaking} aria-hidden="true">
          <span />
          <span />
          <span />
        </span>
        <span className={styles.muted}>Asking…</span>
        {state.audioComplete && (
          <Button variant="ghost" onClick={live.skipAudio}>
            Skip to answer
          </Button>
        )}
      </div>
    );
  }
  if (state.phase === "answering") {
    return (
      <div className={styles.audioRow}>
        <Button variant="ghost" onClick={live.replay}>
          ↻ Hear the question again
        </Button>
      </div>
    );
  }
  return null;
}

function AnswerArea({ live }: { live: LiveInterview }) {
  const { state } = live;

  if (state.phase === "ending") return <Waiting text="Ending the interview…" />;

  if (state.phase === "sending" || state.phase === "preparing") {
    return (
      <div className={styles.answer}>
        {state.transcript && (
          <div className={styles.heard}>
            <p className={styles.heardLabel}>What we heard</p>
            <p className={styles.heardText}>{state.transcript}</p>
          </div>
        )}
        <Waiting
          text={
            state.phase === "sending"
              ? live.typing
                ? "Sending your answer…"
                : "Transcribing your answer…"
              : "Thinking of the next question…"
          }
        />
      </div>
    );
  }

  const canAnswer = state.phase === "answering" || state.phase === "recording";

  return (
    <div className={styles.answer}>
      {state.notice && (
        <p className={styles.notice} role="alert">
          {state.notice}
        </p>
      )}
      {live.micProblem && <p className={styles.notice}>{live.micProblem}</p>}

      {live.typing ? <TypedAnswer live={live} enabled={state.phase === "answering"} /> : <SpokenAnswer live={live} />}

      {!live.micProblem && canAnswer && state.phase !== "recording" && (
        <button type="button" className={styles.switch} onClick={() => live.setTyping(!live.typing)}>
          {live.typing ? "Speak instead" : "Type instead"}
        </button>
      )}
    </div>
  );
}

function SpokenAnswer({ live }: { live: LiveInterview }) {
  const { state } = live;
  const recording = state.phase === "recording";
  const level = useLevel(live.level, recording);
  const remaining = MAX_ANSWER_SECONDS - live.recordingSeconds;

  return (
    <div className={styles.spoken}>
      <MicButton
        recording={recording}
        disabled={state.phase !== "answering" && !recording}
        onClick={recording ? live.stopRecording : live.startRecording}
      />
      <p className={styles.micLabel} aria-live="polite">
        {recording
          ? "Listening. Tap when you're done."
          : state.phase === "answering"
            ? "Tap to answer"
            : "The mic opens when the question finishes"}
      </p>
      {recording && (
        <div className={styles.recordingInfo}>
          <LevelMeter level={level} label="Your voice" />
          <p className={remaining <= 20 ? styles.timerLow : styles.timer}>
            {formatSeconds(live.recordingSeconds)}
            {remaining <= 20 && ` · ${remaining}s left`}
          </p>
        </div>
      )}
    </div>
  );
}

function TypedAnswer({ live, enabled }: { live: LiveInterview; enabled: boolean }) {
  const [text, setText] = useState("");
  const fieldId = useId();

  function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!text.trim()) return;
    live.sendText(text);
    setText("");
  }

  return (
    <form className={styles.typed} onSubmit={handleSubmit}>
      <label htmlFor={fieldId} className="visually-hidden">
        Your answer
      </label>
      <textarea
        id={fieldId}
        className={styles.textarea}
        rows={5}
        maxLength={MAX_TEXT_ANSWER}
        placeholder={enabled ? "Type your answer…" : "You can type once the question finishes."}
        value={text}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) handleSubmit(e);
        }}
        disabled={!enabled}
      />
      <div className={styles.typedActions}>
        <span className={styles.muted}>Ctrl + Enter to send</span>
        <Button type="submit" disabled={!enabled || !text.trim()}>
          Send answer
        </Button>
      </div>
    </form>
  );
}

function Finished({
  handoff,
  answered,
  outcome,
}: {
  handoff: LiveHandoff;
  answered: number;
  outcome: LiveInterview["state"]["outcome"];
}) {
  return (
    <div className={styles.endScreen}>
      <p className={styles.endMark} aria-hidden="true">
        ✓
      </p>
      <h1 className={styles.endTitle}>{outcome === "completed" ? "Interview complete" : "Interview ended"}</h1>
      <p className={styles.endText}>
        You answered {answered} of {QUESTIONS_PER_INTERVIEW} questions. Your report is being prepared against your
        code; it usually takes about a minute.
      </p>
      <div className={styles.endActions}>
        <ButtonLink to={`/interviews/${handoff.interviewId}/report`} size="large">
          See your report
        </ButtonLink>
        <ButtonLink to="/home" variant="ghost">
          Back to home
        </ButtonLink>
      </div>
    </div>
  );
}

function Failed({ handoff, answered, rejected }: { handoff: LiveHandoff; answered: number; rejected: boolean }) {
  return (
    <div className={styles.endScreen}>
      <h1 className={styles.endTitle}>{rejected ? "This interview session has expired" : "The interview was interrupted"}</h1>
      <p className={styles.endText}>
        {rejected
          ? "An interview has to start within 5 minutes of setting it up, and each session can only be used once."
          : answered > 0
            ? `The connection was lost. Your ${answered} answered ${answered === 1 ? "question is" : "questions are"} saved, and you'll get a report on them.`
            : "The connection was lost before you answered a question."}
      </p>
      <div className={styles.endActions}>
        {!rejected && answered > 0 && (
          <ButtonLink to={`/interviews/${handoff.interviewId}/report`} size="large">
            See your report
          </ButtonLink>
        )}
        <ButtonLink
          to={`/repositories/${handoff.repositoryId}/interview`}
          variant={!rejected && answered > 0 ? "secondary" : "primary"}
          size="large"
        >
          Start a new interview
        </ButtonLink>
        <ButtonLink to="/home" variant="ghost">
          Back to home
        </ButtonLink>
      </div>
    </div>
  );
}

function CannotResume({ interviewId }: { interviewId: number }) {
  return (
    <div className={styles.endScreen}>
      <h1 className={styles.endTitle}>This interview can&rsquo;t be reopened</h1>
      <p className={styles.endText}>
        A live interview runs in the tab it started in. If it ended, its report is ready to read; otherwise start a
        new one from your repository.
      </p>
      <div className={styles.endActions}>
        <ButtonLink to={`/interviews/${interviewId}/report`}>See the report</ButtonLink>
        <ButtonLink to="/home" variant="secondary">
          Back to home
        </ButtonLink>
      </div>
    </div>
  );
}

function formatSeconds(total: number): string {
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

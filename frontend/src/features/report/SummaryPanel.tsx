import type { ReportSummary } from "../../api/types";
import { Card } from "../../components/Card";
import { Icon } from "../../components/Icon";
import { ScoreBar } from "../../components/ScoreBar";
import { sourceUrl } from "./api";
import { scoreTone } from "./scoreTone";
import styles from "./SummaryPanel.module.css";

/** The overall score and a one-line takeaway first, then its parts and notes. */
export function SummaryPanel({ summary }: { summary: ReportSummary }) {
  const overall = overallScore(summary);

  return (
    <div className={styles.summary}>
      <Card className={styles.hero}>
        <ScoreRing score={overall} />
        <div className={styles.heroMain}>
          <p className={styles.takeaway}>{takeaway(summary, overall)}</p>
          <p className={styles.hint}>
            {summary.turns_answered} of {summary.turns_asked} questions answered
          </p>
          <div className={styles.parts}>
            <ScoreRow label="Correctness" score={summary.average_correctness} />
            <ScoreRow label="Clarity" score={summary.average_clarity} />
          </div>
        </div>
      </Card>

      {(summary.strengths.length > 0 || summary.improvements.length > 0) && (
        <div className={styles.notes}>
          <NoteCard title="What went well" icon="check" tone={styles.well} items={summary.strengths} />
          <NoteCard title="Work on next" icon="arrow" tone={styles.next} items={summary.improvements} />
        </div>
      )}
    </div>
  );
}

/** The mean of the two averages, or whichever exists. */
function overallScore(summary: ReportSummary): number | null {
  const parts = [summary.average_correctness, summary.average_clarity].filter((s): s is number => s !== null);
  return parts.length === 0 ? null : parts.reduce((a, b) => a + b, 0) / parts.length;
}

function takeaway(summary: ReportSummary, overall: number | null): string {
  if (overall === null) return "No answers were graded, so there's no score yet.";
  const c = summary.average_correctness;
  const k = summary.average_clarity;
  if (c !== null && k !== null && Math.abs(c - k) >= 0.75) {
    return c > k ? "Strong on correctness. Work on explaining it clearly." : "Clear explanations. Work on the details.";
  }
  if (overall >= 4) return "Strong interview. You know this code well.";
  if (overall >= 3) return "Solid foundation, with a few gaps to close.";
  return "Worth revisiting this code before your next round.";
}

const RADIUS = 42;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

function ScoreRing({ score }: { score: number | null }) {
  const filled = score === null ? 0 : (score / 5) * CIRCUMFERENCE;
  return (
    <div className={`${styles.ring} ${styles[scoreTone(score)]}`}>
      <svg viewBox="0 0 100 100" aria-hidden="true">
        <circle cx="50" cy="50" r={RADIUS} className={styles.ringTrack} />
        <circle
          cx="50"
          cy="50"
          r={RADIUS}
          className={styles.ringFill}
          strokeDasharray={`${filled} ${CIRCUMFERENCE}`}
          transform="rotate(-90 50 50)"
        />
      </svg>
      <p className={styles.ringValue} aria-label={score === null ? "Overall: not scored" : `Overall ${score.toFixed(1)} out of 5`}>
        <span className={styles.big}>{score === null ? "–" : score.toFixed(1)}</span>
        <span className={styles.outOf}>of 5</span>
      </p>
    </div>
  );
}

function ScoreRow({ label, score }: { label: string; score: number | null }) {
  return (
    <div className={styles.part}>
      <div className={styles.partHead}>
        <span className={styles.label}>{label}</span>
        <span className={styles.partValue}>{score === null ? "–" : score.toFixed(1)}</span>
      </div>
      <ScoreBar score={score ?? 0} label={score === null ? `${label} not scored` : `${label} ${score.toFixed(1)} out of 5`} />
    </div>
  );
}

function NoteCard({ title, icon, tone, items }: { title: string; icon: "check" | "arrow"; tone: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <section className={`${styles.note} ${tone}`}>
      <h3 className={styles.noteTitle}>
        <span className={styles.noteIcon} aria-hidden="true">
          <Icon name={icon} size={14} />
        </span>
        {title}
      </h3>
      <ul className={styles.items}>
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </section>
  );
}

export function FilesToRevisit({ files, githubUrl }: { files: ReportSummary["files_to_revisit"]; githubUrl: string }) {
  return (
    <ul className={styles.files}>
      {files.map((f) => (
        <li key={f.file} className={styles.file}>
          <Icon name="file" size={16} className={styles.fileIcon} />
          <span className={styles.fileMain}>
            <a href={sourceUrl(githubUrl, { filename: f.file })} target="_blank" rel="noreferrer" className={styles.fileName}>
              {f.file}
            </a>
            <span className={styles.reason}>{f.reason}</span>
          </span>
          <Icon name="external" size={14} className={styles.fileGo} />
        </li>
      ))}
    </ul>
  );
}

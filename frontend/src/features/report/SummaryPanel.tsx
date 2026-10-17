import type { ReportSummary } from "../../api/types";
import { Card } from "../../components/Card";
import { Icon } from "../../components/Icon";
import { ScoreBar } from "../../components/ScoreBar";
import { sourceUrl } from "./api";
import styles from "./SummaryPanel.module.css";

/** The overall score first, then its parts and the takeaways in short lists. */
export function SummaryPanel({ summary }: { summary: ReportSummary }) {
  const overall = overallScore(summary);
  const hasNotes = summary.strengths.length > 0 || summary.improvements.length > 0;

  return (
    <Card className={styles.summary}>
      <div className={styles.scores}>
        <div className={styles.overall}>
          <p className={styles.label}>Overall</p>
          <p className={styles.big}>
            {overall === null ? "–" : overall.toFixed(1)}
            <span className={styles.outOf}> / 5</span>
          </p>
          <p className={styles.hint}>
            {summary.turns_answered} of {summary.turns_asked} questions answered
          </p>
        </div>
        <div className={styles.parts}>
          <ScoreRow label="Correctness" score={summary.average_correctness} />
          <ScoreRow label="Clarity" score={summary.average_clarity} />
        </div>
      </div>

      {summary.turns_graded === 0 && (
        <p className={styles.none}>No answers were graded, so there are no scores yet.</p>
      )}

      {hasNotes && (
        <div className={styles.notes}>
          <NoteList title="What went well" tone={styles.well} items={summary.strengths} />
          <NoteList title="Work on next" tone={styles.next} items={summary.improvements} />
        </div>
      )}
    </Card>
  );
}

/** The mean of the two averages, or whichever exists. */
function overallScore(summary: ReportSummary): number | null {
  const parts = [summary.average_correctness, summary.average_clarity].filter((s): s is number => s !== null);
  return parts.length === 0 ? null : parts.reduce((a, b) => a + b, 0) / parts.length;
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

function NoteList({ title, tone, items }: { title: string; tone: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <section className={styles.note}>
      <h3 className={`${styles.noteTitle} ${tone}`}>{title}</h3>
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
          <div className={styles.fileMain}>
            <a href={sourceUrl(githubUrl, { filename: f.file })} target="_blank" rel="noreferrer" className={styles.fileName}>
              {f.file}
            </a>
            <p className={styles.reason}>{f.reason}</p>
          </div>
        </li>
      ))}
    </ul>
  );
}

import type { ReportSummary } from "../../api/types";
import { Card } from "../../components/Card";
import { ScoreBar } from "../../components/ScoreBar";
import { sourceUrl } from "./api";
import styles from "./SummaryPanel.module.css";

export function SummaryPanel({ summary, githubUrl }: { summary: ReportSummary; githubUrl: string }) {
  const graded = summary.turns_graded > 0;

  return (
    <div className={styles.summary}>
      <Card className={styles.scores}>
        <ScoreTile label="Correctness" hint="Is it true of your code?" score={summary.average_correctness} />
        <ScoreTile label="Clarity" hint="Was it explained well?" score={summary.average_clarity} />
        <div className={styles.tile}>
          <p className={styles.tileLabel}>Answered</p>
          <p className={styles.value}>
            {summary.turns_answered}
            <span className={styles.outOf}> / {summary.turns_asked}</span>
          </p>
          <p className={styles.hint}>questions</p>
        </div>
      </Card>
      {!graded && (
        <p className={styles.none}>
          No answers were graded, so there are no scores. The questions are listed below so you can practise them.
        </p>
      )}

      {(summary.strengths.length > 0 || summary.improvements.length > 0 || summary.files_to_revisit.length > 0) && (
        <div className={styles.notes}>
          <NoteList title="What went well" tone={styles.well} items={summary.strengths} empty="Nothing stood out yet. Keep practising." />
          <NoteList title="Work on next" tone={styles.next} items={summary.improvements} />
          {summary.files_to_revisit.length > 0 && (
            <section className={styles.note}>
              <h3 className={`${styles.noteTitle} ${styles.files}`}>Files to revisit</h3>
              <ul className={styles.fileList}>
                {summary.files_to_revisit.map((f) => (
                  <li key={f.file}>
                    <a href={sourceUrl(githubUrl, { filename: f.file })} target="_blank" rel="noreferrer" className={styles.file}>
                      {f.file}
                    </a>
                    <p className={styles.reason}>{f.reason}</p>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      )}
    </div>
  );
}

function ScoreTile({ label, hint, score }: { label: string; hint: string; score: number | null }) {
  return (
    <div className={styles.tile}>
      <p className={styles.tileLabel}>{label}</p>
      <p className={styles.value}>
        {score === null ? "–" : score.toFixed(1)}
        <span className={styles.outOf}> / 5</span>
      </p>
      {score !== null && <ScoreBar score={score} label={`${label} ${score.toFixed(1)} out of 5`} />}
      <p className={styles.hint}>{hint}</p>
    </div>
  );
}

function NoteList({ title, tone, items, empty }: { title: string; tone: string; items: string[]; empty?: string }) {
  if (items.length === 0 && !empty) return null;
  return (
    <section className={styles.note}>
      <h3 className={`${styles.noteTitle} ${tone}`}>{title}</h3>
      {items.length === 0 ? (
        <p className={styles.reason}>{empty}</p>
      ) : (
        <ul className={styles.items}>
          {items.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      )}
    </section>
  );
}

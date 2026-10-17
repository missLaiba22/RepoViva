import type { TurnEvaluation } from "../../api/types";
import { ScoreBar } from "../../components/ScoreBar";
import { SourceList } from "./SourceChip";
import styles from "./TurnList.module.css";

/** One expandable row per question, in interview order. */
export function TurnList({ turns, githubUrl, label }: { turns: TurnEvaluation[]; githubUrl: string; label: string }) {
  return (
    <ol className={styles.list} aria-label={label}>
      {turns.map((turn) => (
        <li key={turn.seq}>
          <Turn turn={turn} githubUrl={githubUrl} />
        </li>
      ))}
    </ol>
  );
}

function Turn({ turn, githubUrl }: { turn: TurnEvaluation; githubUrl: string }) {
  if (turn.status === "not_answered") {
    return (
      <div className={`${styles.turn} ${styles.quiet}`}>
        <div className={styles.head}>
          <span className={styles.seq}>Q{turn.seq}</span>
          <div className={styles.headMain}>
            <p className={styles.question}>{turn.question}</p>
            <p className={styles.meta}>Not answered</p>
          </div>
        </div>
      </div>
    );
  }

  return (
    <details className={styles.turn}>
      <summary className={styles.head}>
        <span className={styles.seq}>Q{turn.seq}</span>
        <div className={styles.headMain}>
          <p className={styles.question}>{turn.question}</p>
          {turn.status === "graded" ? (
            <p className={styles.pills}>
              <span className={styles.pill}>
                Correctness <strong>{turn.correctness.score}</strong>
              </span>
              <span className={styles.pill}>
                Clarity <strong>{turn.clarity.score}</strong>
              </span>
            </p>
          ) : (
            <p className={styles.meta}>Couldn&rsquo;t be graded</p>
          )}
        </div>
        <span className={styles.chevron} aria-hidden="true" />
      </summary>

      <div className={styles.body}>
        <section>
          <h4 className={styles.label}>Your answer</h4>
          <blockquote className={styles.answer}>{turn.answer}</blockquote>
        </section>

        {turn.status === "not_graded" ? (
          <p className={styles.meta}>
            Not scored, so not counted in your averages.
          </p>
        ) : (
          <>
            <div className={styles.scores}>
              <ScoreDetail label="Correctness" score={turn.correctness.score} text={turn.correctness.justification} />
              <ScoreDetail label="Clarity" score={turn.clarity.score} text={turn.clarity.justification} />
            </div>

            {(turn.strengths.length > 0 || turn.gaps.length > 0) && (
              <div className={styles.pair}>
                {turn.strengths.length > 0 && <Points title="Strengths" tone={styles.well} items={turn.strengths} />}
                {turn.gaps.length > 0 && <Points title="Gaps" tone={styles.gap} items={turn.gaps} />}
              </div>
            )}

            {turn.key_points.length > 0 && (
              <section className={styles.keyPoints}>
                <h4 className={styles.label}>What a strong answer covers</h4>
                <ol>
                  {turn.key_points.map((kp) => (
                    <li key={kp.point}>
                      <p>{kp.point}</p>
                      <SourceList sources={kp.sources} githubUrl={githubUrl} />
                    </li>
                  ))}
                </ol>
              </section>
            )}
          </>
        )}

        {turn.sources.length > 0 && (
          <section className={styles.basedOn}>
            <h4 className={styles.label}>The question was based on</h4>
            <SourceList sources={turn.sources} githubUrl={githubUrl} />
          </section>
        )}
      </div>
    </details>
  );
}

function ScoreDetail({ label, score, text }: { label: string; score: number; text: string }) {
  return (
    <section className={styles.scoreDetail}>
      <div className={styles.scoreHead}>
        <h4 className={styles.label}>{label}</h4>
        <span className={styles.scoreValue}>{score} / 5</span>
      </div>
      <ScoreBar score={score} label={`${label} ${score} out of 5`} />
      <p className={styles.justification}>{text}</p>
    </section>
  );
}

function Points({ title, tone, items }: { title: string; tone: string; items: string[] }) {
  return (
    <section>
      <h4 className={`${styles.label} ${tone}`}>{title}</h4>
      <ul className={styles.points}>
        {items.map((item) => (
          <li key={item}>{item}</li>
        ))}
      </ul>
    </section>
  );
}

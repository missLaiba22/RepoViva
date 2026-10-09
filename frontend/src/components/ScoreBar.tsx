import styles from "./ScoreBar.module.css";

/** A quiet 1–5 bar: no red/green, just how far along the scale. */
export function ScoreBar({ score, max = 5, label }: { score: number; max?: number; label: string }) {
  return (
    <div className={styles.track} role="meter" aria-label={label} aria-valuemin={0} aria-valuemax={max} aria-valuenow={score}>
      <div className={styles.fill} style={{ width: `${(score / max) * 100}%` }} />
    </div>
  );
}

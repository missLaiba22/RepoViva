import styles from "./LevelMeter.module.css";

const BARS = 24;

/** A row of bars that light up with the input level (0–1). */
export function LevelMeter({ level, label = "Microphone level" }: { level: number; label?: string }) {
  const lit = Math.round(Math.min(1, Math.max(0, level)) * BARS);
  return (
    <div
      className={styles.meter}
      role="meter"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(level * 100)}
    >
      {Array.from({ length: BARS }, (_, i) => (
        <span key={i} className={i < lit ? styles.on : styles.off} />
      ))}
    </div>
  );
}

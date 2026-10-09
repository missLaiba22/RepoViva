import styles from "./MicButton.module.css";

/** The one big control: tap to start answering, tap again to send. */
export function MicButton({
  recording,
  disabled,
  onClick,
}: {
  recording: boolean;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={recording ? `${styles.mic} ${styles.recording}` : styles.mic}
      onClick={onClick}
      disabled={disabled}
      aria-label={recording ? "Stop and send answer" : "Start answering"}
      aria-pressed={recording}
    >
      {recording ? (
        <svg width="28" height="28" viewBox="0 0 24 24" aria-hidden="true">
          <rect x="6" y="6" width="12" height="12" rx="2.5" fill="currentColor" />
        </svg>
      ) : (
        <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
          <rect x="9" y="3" width="6" height="11" rx="3" />
          <path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21M8.5 21h7" strokeLinecap="round" />
        </svg>
      )}
    </button>
  );
}

import { useId, useState, type ReactNode } from "react";
import styles from "./ErrorDetails.module.css";

/** "Details": the technical side of a problem, hidden until asked for. Put it
 * in a wrapping flex row of actions; the panel opens on its own line below. */
export function ErrorDetails({ children, technical }: { children?: ReactNode; technical: string | null }) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  return (
    <>
      <button
        type="button"
        className={styles.toggle}
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen(!open)}
      >
        Details
      </button>
      {open && (
        <div id={panelId} className={styles.panel}>
          {children && <p>{children}</p>}
          {technical && <pre className={styles.technical}>{technical}</pre>}
        </div>
      )}
    </>
  );
}

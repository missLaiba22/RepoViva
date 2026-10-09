import { useEffect, useRef } from "react";

/** Call `tick` every `intervalMs` while `active`. Pauses while the tab is hidden. */
export function usePolling(tick: () => void, intervalMs: number, active: boolean): void {
  const tickRef = useRef(tick);
  useEffect(() => {
    tickRef.current = tick;
  }, [tick]);

  useEffect(() => {
    if (!active) return;
    const id = window.setInterval(() => {
      if (document.visibilityState === "visible") tickRef.current();
    }, intervalMs);
    return () => window.clearInterval(id);
  }, [active, intervalMs]);
}

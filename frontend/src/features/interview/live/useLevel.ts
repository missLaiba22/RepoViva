import { useEffect, useState } from "react";

/** Sample `read()` every animation frame while `active`. */
export function useLevel(read: () => number, active: boolean): number {
  const [level, setLevel] = useState(0);

  useEffect(() => {
    if (!active) return;
    let frame = requestAnimationFrame(function tick() {
      setLevel(read());
      frame = requestAnimationFrame(tick);
    });
    return () => {
      cancelAnimationFrame(frame);
      setLevel(0);
    };
  }, [read, active]);

  return level;
}

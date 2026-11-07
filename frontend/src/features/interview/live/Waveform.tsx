import { useEffect, useRef } from "react";
import styles from "./Waveform.module.css";

const BARS = 56;
const SAMPLE_MS = 60;
const GAP = 3;

/** A scrolling waveform of the voice level (0–1), newest on the right.
 * Frozen while paused; colour comes from the CSS `color` of the canvas. */
export function Waveform({ read, paused }: { read: () => number; paused: boolean }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const history = useRef<number[]>(Array(BARS).fill(0));

  useEffect(() => {
    const el = canvas.current;
    const ctx = el?.getContext("2d");
    if (!el || !ctx) return;

    let frame = 0;
    let last = 0;
    const draw = (now: number) => {
      frame = requestAnimationFrame(draw);
      if (now - last < SAMPLE_MS) return;
      last = now;
      if (!paused) history.current = [...history.current.slice(1), read()];

      const ratio = window.devicePixelRatio || 1;
      const width = el.clientWidth;
      const height = el.clientHeight;
      if (el.width !== width * ratio || el.height !== height * ratio) {
        el.width = width * ratio;
        el.height = height * ratio;
      }
      ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
      ctx.clearRect(0, 0, width, height);
      ctx.fillStyle = getComputedStyle(el).color;

      const bar = (width - GAP * (BARS - 1)) / BARS;
      history.current.forEach((level, i) => {
        const h = Math.max(3, Math.min(1, level * 1.4) * height);
        ctx.beginPath();
        ctx.roundRect(i * (bar + GAP), (height - h) / 2, bar, h, bar / 2);
        ctx.fill();
      });
    };
    frame = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(frame);
  }, [read, paused]);

  return (
    <canvas
      ref={canvas}
      className={paused ? `${styles.wave} ${styles.paused}` : styles.wave}
      role="img"
      aria-label={paused ? "Recording paused" : "Your voice"}
    />
  );
}

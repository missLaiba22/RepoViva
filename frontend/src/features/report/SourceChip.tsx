import type { Source } from "../../api/types";
import { sourceUrl } from "./api";
import styles from "./SourceChip.module.css";

/** `file.py:12–40`, linking to those lines on GitHub. */
export function SourceChip({ source, githubUrl }: { source: Source; githubUrl: string }) {
  const name = source.filename.split("/").pop() ?? source.filename;
  const lines = source.start_line === source.end_line ? `${source.start_line}` : `${source.start_line}–${source.end_line}`;
  return (
    <a
      className={styles.chip}
      href={sourceUrl(githubUrl, source)}
      target="_blank"
      rel="noreferrer"
      title={`${source.filename}, lines ${lines}`}
    >
      {name}
      <span className={styles.lines}>:{lines}</span>
    </a>
  );
}

export function SourceList({ sources, githubUrl }: { sources: Source[]; githubUrl: string }) {
  // The same chunk can back several points; show each once.
  const unique = sources.filter((s, i) => sources.findIndex((o) => o.chunk_id === s.chunk_id) === i);
  return (
    <span className={styles.list}>
      {unique.map((s) => (
        <SourceChip key={s.chunk_id} source={s} githubUrl={githubUrl} />
      ))}
    </span>
  );
}

import { useCallback, type ReactNode } from "react";
import type { Repository, RepositoryArea } from "../../api/types";
import { Card } from "../../components/Card";
import { Facts } from "../../components/Facts";
import { Icon, type IconName } from "../../components/Icon";
import { useResource } from "../../hooks/useResource";
import { formatDate, formatRelative } from "../../lib/format";
import { getRepositoryAreas } from "./api";
import styles from "./RepositoryOverview.module.css";

// Mirrors repository-service indexing/flow.py; update both together.
const FILE_TYPES = ["Python", "JavaScript", "TypeScript", "Go", "Rust", "Java", "Ruby", "Markdown & READMEs"];

const SKIPPED = [
  "Dependencies (node_modules, .venv, vendor)",
  "Build output (dist, build)",
  "Lock files",
  "Translated docs",
  "Files over 500 KB",
];

/** What RepoViva analyzed in this repository, so the user knows what the
 * interview will cover before starting it. */
export function RepositoryOverview({ repository }: { repository: Repository }) {
  return (
    <section className={styles.section} aria-labelledby="overview-heading">
      <h2 id="overview-heading" className={styles.sectionTitle}>
        Repository overview
      </h2>
      <Card className={styles.card}>
        <Facts
          label="Repository details"
          items={[
            { icon: "repo", label: `Connected ${formatDate(repository.created_at)}` },
            { icon: "check", label: `Prepared ${formatRelative(repository.updated_at)}` },
          ]}
        />
        <Areas repositoryId={repository.id} />
        <div className={styles.grid}>
          <Block icon="file" title="Files RepoViva reads">
            <ul className={styles.chips} aria-label="File types read">
              {FILE_TYPES.map((type) => (
                <li key={type} className={styles.chip}>
                  {type}
                </li>
              ))}
            </ul>
          </Block>
          <Block icon="stop" title="What it skips">
            <ul className={styles.list}>
              {SKIPPED.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </Block>
        </div>
      </Card>
    </section>
  );
}

/** Quietly absent if the areas can't load: the rest of the overview still helps. */
function Areas({ repositoryId }: { repositoryId: number }) {
  const load = useCallback(() => getRepositoryAreas(repositoryId), [repositoryId]);
  const areas = useResource(load);
  if (areas.state === "error") return null;

  return (
    <Block icon="folder" title="Code areas your questions come from">
      <p className={styles.caption}>
        Each question focuses on one of these areas, and your answer is graded against its code.
      </p>
      {areas.state === "loading" ? (
        <p className={styles.caption}>Loading code areas…</p>
      ) : areas.data.length === 0 ? (
        <p className={styles.caption}>No code areas were found.</p>
      ) : (
        <AreaList areas={areas.data} />
      )}
    </Block>
  );
}

function AreaList({ areas }: { areas: RepositoryArea[] }) {
  const total = areas.reduce((sum, area) => sum + area.chunk_count, 0);
  const largest = areas[0].chunk_count;
  return (
    <ul className={styles.areas} aria-label="Code areas">
      {areas.map((area) => (
        <li key={area.path} className={styles.area}>
          <span className={styles.areaPath}>
            <Icon name={area.path.endsWith("/") ? "folder" : "file"} size={14} />
            {area.path}
          </span>
          <span className={styles.bar} aria-hidden="true">
            <span style={{ width: `${(area.chunk_count / largest) * 100}%` }} />
          </span>
          <span className={styles.share}>{Math.round((area.chunk_count / total) * 100)}%</span>
        </li>
      ))}
    </ul>
  );
}

function Block({ icon, title, children }: { icon: IconName; title: string; children: ReactNode }) {
  return (
    <div className={styles.block}>
      <h3 className={styles.blockTitle}>
        <Icon name={icon} size={16} />
        {title}
      </h3>
      {children}
    </div>
  );
}

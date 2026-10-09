/** "https://github.com/owner/name(.git)" → { owner, name }. Falls back to the raw URL. */
export function repoName(githubUrl: string): { owner: string; name: string } {
  const match = githubUrl.match(/github\.com\/([^/]+)\/([^/#?]+?)(?:\.git)?\/?$/i);
  if (!match) return { owner: "", name: githubUrl };
  return { owner: match[1], name: match[2] };
}

const dateFormat = new Intl.DateTimeFormat(undefined, { day: "numeric", month: "short", year: "numeric" });
const timeFormat = new Intl.DateTimeFormat(undefined, { hour: "numeric", minute: "2-digit" });

export function formatDate(iso: string): string {
  return dateFormat.format(new Date(iso));
}

export function formatDateTime(iso: string): string {
  const d = new Date(iso);
  return `${dateFormat.format(d)}, ${timeFormat.format(d)}`;
}

/** Whole minutes between two timestamps, at least 1. Null if either is missing. */
export function durationMinutes(start: string | null, end: string | null): number | null {
  if (!start || !end) return null;
  const ms = new Date(end).getTime() - new Date(start).getTime();
  return Math.max(1, Math.round(ms / 60000));
}

/** "just now", "4 min ago", "2 h ago", then a date. */
export function formatRelative(iso: string, now: Date = new Date()): string {
  const minutes = Math.floor((now.getTime() - new Date(iso).getTime()) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  return `on ${formatDate(iso)}`;
}

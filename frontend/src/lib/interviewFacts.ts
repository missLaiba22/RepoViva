import type { IconName } from "../components/Icon";

export const INTERVIEW_FACTS: { icon: IconName; label: string }[] = [
  { icon: "list", label: "Up to 6 questions" },
  // Voice Service's MAX_SESSION_SECONDS (1800) ends every interview at 30 minutes.
  { icon: "clock", label: "Up to 30 min" },
  { icon: "stop", label: "Stop anytime" },
];

/** 4+ is strong, 3 is fair, below is weak: shared by the score ring and the pills. */
export function scoreTone(score: number | null): "strong" | "fair" | "weak" | "none" {
  if (score === null) return "none";
  if (score >= 4) return "strong";
  if (score >= 3) return "fair";
  return "weak";
}

import { describe, expect, it } from "vitest";
import { normalizeGithubUrl } from "../src/features/repositories/githubUrl";

describe("normalizeGithubUrl", () => {
  it.each([
    "https://github.com/tiangolo/fastapi",
    "https://github.com/tiangolo/fastapi/",
    "https://github.com/tiangolo/fastapi.git",
    "http://github.com/tiangolo/fastapi",
    "https://www.github.com/tiangolo/fastapi",
    "github.com/tiangolo/fastapi",
    "tiangolo/fastapi",
    "  https://github.com/tiangolo/fastapi  ",
    "https://github.com/tiangolo/fastapi/tree/master/docs",
    "https://github.com/tiangolo/fastapi/blob/master/README.md",
    "https://github.com/tiangolo/fastapi#readme",
    "https://github.com/tiangolo/fastapi?tab=readme",
  ])("%s → canonical", (input) => {
    expect(normalizeGithubUrl(input)).toBe("https://github.com/tiangolo/fastapi");
  });

  it("keeps dots, dashes and underscores in names", () => {
    expect(normalizeGithubUrl("github.com/my-org/my_repo.js")).toBe("https://github.com/my-org/my_repo.js");
  });

  it.each([
    "",
    "fastapi",
    "https://gitlab.com/owner/repo",
    "https://github.com/owner",
    "https://github.com/",
    "https://github.com/../repo",
    "https://evil.com/github.com/owner/repo",
    "owner/repo/extra",
  ])("%j → null", (input) => {
    expect(normalizeGithubUrl(input)).toBeNull();
  });
});

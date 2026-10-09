import { describe, expect, it } from "vitest";
import { durationMinutes, repoName } from "../src/lib/format";

describe("repoName", () => {
  it.each([
    ["https://github.com/tiangolo/fastapi", { owner: "tiangolo", name: "fastapi" }],
    ["https://github.com/tiangolo/fastapi.git", { owner: "tiangolo", name: "fastapi" }],
    ["https://github.com/tiangolo/fastapi/", { owner: "tiangolo", name: "fastapi" }],
    ["not a url", { owner: "", name: "not a url" }],
  ])("%s", (url, expected) => {
    expect(repoName(url)).toEqual(expected);
  });
});

describe("durationMinutes", () => {
  it("rounds to whole minutes, at least 1", () => {
    expect(durationMinutes("2026-10-08T10:00:00Z", "2026-10-08T10:14:20Z")).toBe(14);
    expect(durationMinutes("2026-10-08T10:00:00Z", "2026-10-08T10:00:10Z")).toBe(1);
  });

  it("is null when either end is missing", () => {
    expect(durationMinutes(null, "2026-10-08T10:00:00Z")).toBeNull();
    expect(durationMinutes("2026-10-08T10:00:00Z", null)).toBeNull();
  });
});

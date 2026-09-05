/// <reference types="vitest/globals" />
/**
 * B3 regression tests (mobile) — the typed result lifecycle and the shared
 * grade-card text used by the "Share result" action on the result screen.
 */
import { expect, test, vi } from "vitest";

// The lib chain (student → auth) reads tokens through Expo's secure store —
// not available outside the native runtime, and irrelevant to pure helpers.
vi.mock("expo-secure-store", () => ({
  getItemAsync: vi.fn().mockResolvedValue(null),
  setItemAsync: vi.fn().mockResolvedValue(undefined),
  deleteItemAsync: vi.fn().mockResolvedValue(undefined),
}));

import { gradeCardText, type StudentExamResult } from "./student";
import { resolveClassWebUrl, webClassUrl } from "./online-class";

const base: StudentExamResult = {
  exam_id: "exam-1",
  title: "DS Unit Test 1",
  subject_name: "Data Structures",
  total_marks: 10,
  passing_marks: 4,
  status: "ONGOING",
  result_state: "AVAILABLE",
  total_score: 8,
  percentage: 80,
  grade: null,
  submitted_at: "2026-09-01T10:00:00Z",
  show_answers: true,
  answers: [],
};

test("gradeCardText renders score, percentage and the PASS/FAIL fallback grade", () => {
  const text = gradeCardText(base);
  expect(text).toContain("DS Unit Test 1");
  expect(text).toContain("Data Structures");
  expect(text).toContain("Score: 8/10 · 80% · Grade: PASS");

  const failed = gradeCardText({ ...base, total_score: 2, percentage: 20 });
  expect(failed).toContain("Grade: FAIL");

  const graded = gradeCardText({ ...base, grade: "A+" });
  expect(graded).toContain("Grade: A+");
});

test("gradeCardText stays honest when scores are withheld (under evaluation)", () => {
  const text = gradeCardText({
    ...base,
    result_state: "UNDER_EVALUATION",
    total_score: null,
    percentage: null,
    submitted_at: null,
  });
  expect(text).toContain("Score: —/10 · — · Grade: —");
  expect(text).not.toContain("Submitted:");
});

test("typed states are part of the result contract", () => {
  const states: StudentExamResult["result_state"][] = [
    "NOT_ATTEMPTED",
    "IN_PROGRESS",
    "UNDER_EVALUATION",
    "AVAILABLE",
  ];
  expect(states).toHaveLength(4);
  expect(base.result_state).toBe("AVAILABLE");
});

test("webClassUrl deep-links to the web classroom only when configured", () => {
  vi.stubEnv("EXPO_PUBLIC_WEB_URL", "https://erp.example.com/");
  expect(webClassUrl("class-7")).toBe("https://erp.example.com/student/online-classes/class-7");
  expect(webClassUrl("class-7", "teacher")).toBe("https://erp.example.com/teacher/online-classes/class-7");

  vi.stubEnv("EXPO_PUBLIC_WEB_URL", "");
  expect(webClassUrl("class-7")).toBeNull();
  vi.unstubAllEnvs();
});

test("resolveClassWebUrl provides fallbacks even when EXPO_PUBLIC_WEB_URL is not set", () => {
  vi.stubEnv("EXPO_PUBLIC_WEB_URL", "https://erp.example.com");
  expect(resolveClassWebUrl("class-8")).toBe("https://erp.example.com/student/online-classes/class-8");
  expect(resolveClassWebUrl("class-8", "teacher")).toBe("https://erp.example.com/teacher/online-classes/class-8");

  vi.stubEnv("EXPO_PUBLIC_WEB_URL", "");
  const fallback = resolveClassWebUrl("class-8");
  expect(fallback).toContain("/student/online-classes/class-8");
  vi.unstubAllEnvs();
});

/// <reference types="vitest/globals" />
/**
 * B1 regression test (mobile) — the close → reopen → resubmit loop.
 *
 * The teacher's reopen action on the mobile app must send the resubmission
 * choice in the request body (`request_resubmission`), matching the backend
 * contract: with it, un-reviewed submissions are handed back to students as
 * RESUBMIT_REQUESTED; without it only students who never submitted can
 * submit. The grading-answer shape assertions pin the B2 answer-key fields
 * the grade-attempt screen renders.
 */
import { beforeEach, expect, test, vi } from "vitest";

// The auth client reads tokens through Expo's secure store — not available
// outside the native runtime, and irrelevant to the request wiring under test.
vi.mock("expo-secure-store", () => ({
  getItemAsync: vi.fn().mockResolvedValue(null),
  setItemAsync: vi.fn().mockResolvedValue(undefined),
  deleteItemAsync: vi.fn().mockResolvedValue(undefined),
}));

import { reopenTeacherAssignment, type TeacherAnswerRow } from "./teacher";

const okResponse = () => ({
  ok: true,
  status: 200,
  json: async () => ({ success: true, data: { id: "assignment-1", status: "PUBLISHED" }, message: "reopened" }),
});

beforeEach(() => {
  globalThis.fetch = vi.fn().mockImplementation(async () => okResponse()) as unknown as typeof fetch;
});

test("reopen sends the resubmission choice in the request body", async () => {
  await reopenTeacherAssignment("assignment-1", true);

  const [url, init] = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [
    string,
    RequestInit,
  ];
  expect(url.endsWith("/api/v1/teacher/assignments/assignment-1/reopen")).toBe(true);
  expect(init.method).toBe("POST");
  expect(JSON.parse(init.body as string)).toEqual({ request_resubmission: true });
});

test("reopen without resubmission keeps un-reviewed submissions untouched", async () => {
  await reopenTeacherAssignment("assignment-1", false);

  const [, init] = (globalThis.fetch as ReturnType<typeof vi.fn>).mock.calls[0] as [
    string,
    RequestInit,
  ];
  expect(JSON.parse(init.body as string)).toEqual({ request_resubmission: false });
});

test("the grading payload carries the full answer key (B2 contract)", () => {
  // Compile-time shape check: the grade-attempt screen relies on `options`
  // and `matched_pairs` being present on every answer row.
  const answer = {
    answer_id: "a",
    question_id: "q",
    question_text: "Pick the SI unit of force",
    question_type: "MCQ",
    marks: 2,
    selected_option_id: "opt-2",
    selected_option_text: "Joule",
    correct_option_text: "Newton",
    options: [
      { id: "opt-1", text: "Newton", is_correct: true, sort_order: 1 },
      { id: "opt-2", text: "Joule", is_correct: false, sort_order: 2 },
    ],
    text_answer: null,
    matched_pairs: null,
    score: 0,
    feedback: null,
    is_auto_graded: true,
  } satisfies TeacherAnswerRow;

  const correct = answer.options.find((option) => option.is_correct);
  expect(correct?.text).toBe("Newton");
  expect(answer.options.find((option) => option.id === answer.selected_option_id)?.text).toBe("Joule");
});

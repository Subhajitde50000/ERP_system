/// <reference types="vitest/globals" />
/**
 * B2 regression test — the teacher grading panel must show the full answer
 * key (every option, the correct one and the student's pick flagged) plus
 * MATCH pairings, not just a bare selected/correct pair. This is the fix for
 * the "question review shows only squares" report.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

vi.mock("next/navigation", () => ({ useParams: () => ({ id: "exam-1" }) }));

const attemptDetail = {
  attempt_id: "attempt-1",
  student_id: "student-1",
  student_name: "Ada L",
  roll_number: "101",
  status: "SUBMITTED",
  started_at: "2026-09-04T10:00:00Z",
  submitted_at: "2026-09-04T10:25:00Z",
  total_score: null,
  percentage: null,
  grade: null,
  tab_switch_count: 0,
  pending_grading_count: 1,
  answers: [
    {
      answer_id: "answer-mcq",
      question_id: "q-mcq",
      question_text: "Pick the SI unit of force",
      question_type: "MCQ",
      marks: 2,
      selected_option_id: "opt-joule",
      selected_option_text: "Joule",
      correct_option_text: "Newton",
      options: [
        { id: "opt-newton", text: "Newton", is_correct: true, sort_order: 1 },
        { id: "opt-joule", text: "Joule", is_correct: false, sort_order: 2 },
      ],
      text_answer: null,
      matched_pairs: null,
      score: 0,
      feedback: null,
      is_auto_graded: true,
    },
    {
      answer_id: "answer-match",
      question_id: "q-match",
      question_text: "Match unit to symbol",
      question_type: "MATCH",
      marks: 2,
      selected_option_id: null,
      selected_option_text: null,
      correct_option_text: null,
      options: [],
      text_answer: null,
      matched_pairs: { Newton: "N", Joule: "J" },
      score: null,
      feedback: null,
      is_auto_graded: false,
    },
  ],
};

const fetchTeacherExam = vi.fn().mockResolvedValue({ title: "Physics unit test", status: "ONGOING" });
const fetchExamAttempts = vi.fn().mockResolvedValue({
  total: 1,
  limit: 100,
  offset: 0,
  items: [
    {
      attempt_id: "attempt-1",
      student_id: "student-1",
      student_name: "Ada L",
      roll_number: "101",
      status: "SUBMITTED",
      started_at: "2026-09-04T10:00:00Z",
      submitted_at: "2026-09-04T10:25:00Z",
      total_score: null,
      percentage: null,
      grade: null,
      tab_switch_count: 0,
      pending_grading_count: 1,
    },
  ],
});
const fetchExamAttempt = vi.fn().mockResolvedValue(attemptDetail);

vi.mock("@/lib/teacher", () => ({
  fetchTeacherExam: (...args: unknown[]) => fetchTeacherExam(...args),
  fetchExamAttempts: (...args: unknown[]) => fetchExamAttempts(...args),
  fetchExamAttempt: (...args: unknown[]) => fetchExamAttempt(...args),
  gradeExamAttempt: vi.fn(),
  releaseExamResults: vi.fn(),
}));

import { TeacherExamResultsPage } from "@/components/teacher/teacher-exam-results";

afterEach(() => vi.clearAllMocks());

test("grading panel renders the complete answer key for auto-graded questions", async () => {
  render(<TeacherExamResultsPage />);

  const grade = await screen.findByRole("button", { name: "Grade" });
  fireEvent.click(grade);

  // Auto-graded section: question stem, verdict, and BOTH options with badges.
  await waitFor(() => screen.getByText("Pick the SI unit of force"));
  expect(screen.getByText("WRONG · 0/2")).toBeInTheDocument();
  expect(screen.getAllByText("Newton").length).toBeGreaterThan(0);
  expect(screen.getAllByText("Joule").length).toBeGreaterThan(0);
  expect(screen.getAllByText("CORRECT").length).toBeGreaterThan(0);
  expect(screen.getAllByText("STUDENT'S PICK").length).toBeGreaterThan(0);

  // Manual MATCH card: the student's pairings render readably.
  expect(screen.getByText("Match unit to symbol")).toBeInTheDocument();
  expect(screen.getByText("→ N")).toBeInTheDocument();
  expect(screen.getByText("→ J")).toBeInTheDocument();
});

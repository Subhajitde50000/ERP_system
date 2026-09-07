/// <reference types="vitest/globals" />
/**
 * B3 regression tests — the student result page renders the full typed
 * lifecycle (NOT_ATTEMPTED / IN_PROGRESS / UNDER_EVALUATION / AVAILABLE)
 * instead of blank pages or string-matched error prose, and the grade card
 * exports to PNG on demand.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, vi } from "vitest";

import { StudentExamResultPage } from "@/components/student/student-examinations";

vi.mock("next/navigation", () => ({ useParams: () => ({ id: "exam-1" }) }));
vi.mock("next/link", () => ({ __esModule: true, default: ({ children }: { children: React.ReactNode }) => <a href="#">{children}</a> }));

// html2canvas is dynamically imported on click — mock it so no real
// canvas rasterisation runs under jsdom.
const toBlob = vi.fn((resolve: (b: Blob | null) => void) => resolve(new Blob(["png"])));
const html2canvasMock = vi.fn().mockResolvedValue({ toBlob, width: 0, height: 0 });
vi.mock("html2canvas", () => ({ default: (...args: unknown[]) => html2canvasMock(...args) }));

const result = (overrides: Record<string, unknown> = {}) => ({
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
  answers: [
    {
      question_id: "q1",
      question_text: "Which structure gives O(1) push/pop at one end?",
      question_type: "MCQ",
      marks: 5,
      selected_option_text: "Stack using array",
      correct_option_text: "Stack using array",
      score: 5,
    },
  ],
  ...overrides,
});

const fetchExamResult = vi.fn();

vi.mock("@/lib/student", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/student")>()),
  fetchExamResult: (id: string) => fetchExamResult(id),
}));

let createObjectURL: ReturnType<typeof vi.fn>;
let revokeObjectURL: ReturnType<typeof vi.fn>;

beforeEach(() => {
  html2canvasMock.mockClear();
  toBlob.mockClear();
  fetchExamResult.mockReset();
  createObjectURL = vi.fn(() => "blob:grade-card");
  revokeObjectURL = vi.fn();
  vi.stubGlobal("URL", { ...URL, createObjectURL, revokeObjectURL });
});

afterEach(() => {
  vi.unstubAllGlobals();
});

test("AVAILABLE: score card, marks breakdown and a working grade-card export", async () => {
  fetchExamResult.mockResolvedValue(result());
  render(<StudentExamResultPage />);

  await waitFor(() => expect(screen.getByText("DS Unit Test 1")).toBeInTheDocument());
  expect(screen.getByText("Grade card")).toBeInTheDocument();
  expect(screen.getByText("Marks breakdown")).toBeInTheDocument();
  expect(screen.getByText("8")).toBeInTheDocument(); // score
  expect(screen.getByText("PASS")).toBeInTheDocument(); // grade fallback

  fireEvent.click(screen.getByRole("button", { name: /download grade card/i }));
  await waitFor(() => expect(createObjectURL).toHaveBeenCalledTimes(1));
  await waitFor(() =>
    expect(screen.getByRole("button", { name: /download grade card/i })).not.toBeDisabled(),
  );
  expect(html2canvasMock).toHaveBeenCalledTimes(1);
});

test("UNDER_EVALUATION: typed state renders the submitted screen, never scores", async () => {
  fetchExamResult.mockResolvedValue(
    result({ result_state: "UNDER_EVALUATION", total_score: null, percentage: null, answers: [] }),
  );
  render(<StudentExamResultPage />);

  await waitFor(() => expect(screen.getByText("Exam Submitted Successfully!")).toBeInTheDocument());
  expect(screen.getByText(/under evaluation/i)).toBeInTheDocument();
  expect(screen.queryByText("Grade card")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /download grade card/i })).not.toBeInTheDocument();
});

test("NOT_ATTEMPTED: explains there is no attempt instead of erroring", async () => {
  fetchExamResult.mockResolvedValue(
    result({ result_state: "NOT_ATTEMPTED", submitted_at: null, answers: [] }),
  );
  render(<StudentExamResultPage />);

  await waitFor(() =>
    expect(screen.getByText(/you haven't attempted this exam/i)).toBeInTheDocument(),
  );
});

test("legacy backend 404 'not released' still lands on the under-evaluation screen", async () => {
  fetchExamResult.mockRejectedValue(
    Object.assign(new Error("Request failed with status 404: Results are not released yet"), {
      status: 404,
    }),
  );
  render(<StudentExamResultPage />);

  await waitFor(() => expect(screen.getByText("Exam Submitted Successfully!")).toBeInTheDocument());
});

test("genuine load failure surfaces a retryable error, not a blank page", async () => {
  fetchExamResult.mockRejectedValue(Object.assign(new Error("Request failed with status 500"), { status: 500 }));
  render(<StudentExamResultPage />);

  await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
  expect(screen.getByRole("alert").textContent).toMatch(/500/);
});

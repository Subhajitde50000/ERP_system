/// <reference types="vitest/globals" />
/**
 * B1 regression test — the close → reopen → resubmit loop.
 *
 * 1. A teacher reopening a closed assignment chooses what happens to
 *    un-reviewed work; the request body must carry that choice
 *    (`request_resubmission`), not fire a blind reopen.
 * 2. After reopen, a student whose submission came back as
 *    RESUBMIT_REQUESTED sees the assignment as actionable again (Submit /
 *    Resubmit entry point), instead of it disappearing from their list.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

vi.mock("next/navigation", () => ({ useParams: () => ({ id: "assignment-1" }) }));

const baseAssignment = {
  id: "assignment-1",
  title: "Newton's laws worksheet",
  class_id: "class-1",
  class_name: "Class X-A",
  subject_id: "subject-1",
  subject_code: "PHY",
  subject_name: "Physics",
  assignment_type: "REGULAR",
  total_marks: 20,
  due_date: "2026-09-10T18:00:00Z",
  status: "CLOSED",
  milestone_count: 0,
  student_count: 1,
  group_count: 0,
  submission_count: 1,
  pending_review_count: 1,
  reviewed_count: 0,
  description: "Solve all problems.",
  passing_marks: 8,
  allow_late_submission: false,
  late_penalty_percent: 0,
  max_file_size_mb: 10,
  allowed_file_types: ["pdf"],
  min_group_size: 2,
  max_group_size: 6,
  instructions_url: null,
  created_at: "2026-09-01T10:00:00Z",
  milestones: [],
};

const fetchTeacherAssignment = vi.fn().mockResolvedValue(baseAssignment);
const reopenTeacherAssignment = vi
  .fn()
  .mockResolvedValue({ ...baseAssignment, status: "PUBLISHED" });
const publishTeacherAssignment = vi.fn();
const closeTeacherAssignment = vi.fn();
const updateTeacherAssignment = vi.fn();
const addAssignmentMilestone = vi.fn();
const updateAssignmentMilestone = vi.fn();
const deleteAssignmentMilestone = vi.fn();

vi.mock("@/lib/teacher", () => ({
  fetchTeacherAssignment: (...args: unknown[]) => fetchTeacherAssignment(...args),
  reopenTeacherAssignment: (...args: unknown[]) => reopenTeacherAssignment(...args),
  publishTeacherAssignment: (...args: unknown[]) => publishTeacherAssignment(...args),
  closeTeacherAssignment: (...args: unknown[]) => closeTeacherAssignment(...args),
  updateTeacherAssignment: (...args: unknown[]) => updateTeacherAssignment(...args),
  addAssignmentMilestone: (...args: unknown[]) => addAssignmentMilestone(...args),
  updateAssignmentMilestone: (...args: unknown[]) => updateAssignmentMilestone(...args),
  deleteAssignmentMilestone: (...args: unknown[]) => deleteAssignmentMilestone(...args),
}));

const fetchStudentAssignments = vi.fn().mockResolvedValue({
  total: 2,
  limit: 100,
  offset: 0,
  items: [
    {
      id: "assignment-1",
      title: "Newton's laws worksheet",
      subject_name: "Physics",
      subject_code: "PHY",
      teacher_name: "Ms. Feynman",
      assignment_type: "REGULAR",
      total_marks: 20,
      due_date: "2026-09-10T18:00:00Z",
      status: "PUBLISHED",
      my_status: "RESUBMIT_REQUESTED",
      my_score: null,
      my_submitted_at: "2026-09-03T09:00:00Z",
      is_late: false,
    },
    {
      id: "assignment-2",
      title: "Optics reading",
      subject_name: "Physics",
      subject_code: "PHY",
      teacher_name: "Ms. Feynman",
      assignment_type: "REGULAR",
      total_marks: 10,
      due_date: "2026-09-12T18:00:00Z",
      status: "PUBLISHED",
      my_status: "SUBMITTED",
      my_score: null,
      my_submitted_at: "2026-09-02T09:00:00Z",
      is_late: false,
    },
  ],
});

vi.mock("@/lib/student", () => ({
  fetchStudentAssignments: (...args: unknown[]) => fetchStudentAssignments(...args),
}));

import { TeacherAssignmentDetailPage } from "@/components/teacher/teacher-assignments";
import { StudentAssignmentsPage } from "@/components/student/student-assignments";

afterEach(() => vi.clearAllMocks());

test("teacher reopen asks what to do with un-reviewed submissions and sends the choice", async () => {
  const first = render(<TeacherAssignmentDetailPage />);

  fireEvent.click(await screen.findByRole("button", { name: /Reopen assignment/ }));

  // The choice dialog appears; no request has been sent yet.
  expect(screen.getByRole("dialog", { name: "Reopen assignment" })).toBeInTheDocument();
  expect(reopenTeacherAssignment).not.toHaveBeenCalled();

  fireEvent.click(screen.getByRole("button", { name: /Reopen & ask students to resubmit/ }));
  await waitFor(() =>
    expect(reopenTeacherAssignment).toHaveBeenCalledWith("assignment-1", true),
  );

  // After the reopen the assignment is PUBLISHED again — the reopen button is
  // correctly gone. Mount a fresh closed page for the lighter variant:
  // reopen only for students who never submitted.
  first.unmount();
  const second = render(<TeacherAssignmentDetailPage />);
  fireEvent.click(await second.findByRole("button", { name: /Reopen assignment/ }));
  fireEvent.click(screen.getByRole("button", { name: /Reopen for new submissions only/ }));
  await waitFor(() =>
    expect(reopenTeacherAssignment).toHaveBeenCalledWith("assignment-1", false),
  );
  second.unmount();
});

test("a reopened assignment handed back as RESUBMIT_REQUESTED stays actionable for the student", async () => {
  render(<StudentAssignmentsPage />);

  const reopened = await screen.findByText("Newton's laws worksheet");
  const row = reopened.closest("tr");
  expect(row).not.toBeNull();
  // The actionable entry point: this row offers "Submit" (resubmit), while a
  // plain SUBMITTED row offers only "Open".
  expect(row).toHaveTextContent(/Resubmit Requested/i);
  expect(withinRowLink(row, "Submit")).toBeTruthy();
  const submittedRow = screen.getByText("Optics reading").closest("tr");
  expect(withinRowLink(submittedRow, "Open")).toBeTruthy();
});

function withinRowLink(row: HTMLElement | null, label: string): HTMLElement | null {
  if (!row) return null;
  return Array.from(row.querySelectorAll("a")).find((a) => a.textContent === label) ?? null;
}

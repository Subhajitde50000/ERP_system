/// <reference types="vitest/globals" />
/**
 * Mentor console + allocation board render against real API payloads.
 *
 * `tests/fixtures/mentor-api.json` was captured from a live backend seeded
 * with two classes, one project team and mixed attendance, so the shapes are
 * exactly what `backend/app/schemas/mentor.py` emits. Every page must render
 * from them without throwing, and the note / assignment flows must call the
 * right client functions and update the screen from the returned rows.
 */
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { vi } from "vitest";

import fixtures from "./fixtures/mentor-api.json";

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "x" }),
  usePathname: () => "/mentor/dashboard",
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));
vi.mock("@/hooks/use-institution-auth", () => ({
  useInstitutionAuth: () => ({
    user: { name: "Tina Teacher", roles: ["TEACHER", "MENTOR"] },
    hasRole: (role: string) => ["TEACHER", "MENTOR"].includes(role),
    logout: vi.fn(),
    isAuthenticated: true,
    isLoading: false,
  }),
}));

const api = vi.hoisted(() => ({
  fetchMentorDashboard: vi.fn(),
  fetchMentorMentees: vi.fn(),
  fetchMentorMentee: vi.fn(),
  fetchMentorClasses: vi.fn(),
  fetchMentorTeams: vi.fn(),
  fetchMentorTeam: vi.fn(),
  fetchMentorNotes: vi.fn(),
  createMentorNote: vi.fn(),
  updateMentorNote: vi.fn(),
  deleteMentorNote: vi.fn(),
  fetchMentorNotices: vi.fn(),
  fetchMentorNotice: vi.fn(),
  fetchMentorBoard: vi.fn(),
  assignMentor: vi.fn(),
  removeMentorAssignment: vi.fn(),
}));
vi.mock("@/lib/mentor", async (importOriginal) => ({ ...(await importOriginal<object>()), ...api }));

import { MentorAssignmentsBoardPage } from "@/components/mentor/mentor-assignments-board";
import { MentorClassesPage } from "@/components/mentor/mentor-classes";
import { MentorDashboardPage } from "@/components/mentor/mentor-dashboard";
import { MentorMenteeDetailPage } from "@/components/mentor/mentor-mentee-detail";
import { MentorMenteesPage } from "@/components/mentor/mentor-mentees";
import { MentorNotesPage } from "@/components/mentor/mentor-notes";
import { MentorNoticesPage } from "@/components/mentor/mentor-notices";
import { MentorShell } from "@/components/mentor/mentor-shell";
import { MentorTeamDetailPage, MentorTeamsPage } from "@/components/mentor/mentor-teams";

const STUDENT_TWO = "b0000000-0000-0000-0000-000000000002";
const TEAM = "77777777-7777-7777-7777-777777777771";

beforeEach(() => {
  vi.clearAllMocks();
  api.fetchMentorDashboard.mockResolvedValue(fixtures.dashboard);
  api.fetchMentorMentees.mockResolvedValue(fixtures.mentees);
  api.fetchMentorMentee.mockResolvedValue(fixtures.menteeDetail);
  api.fetchMentorClasses.mockResolvedValue(fixtures.classes);
  api.fetchMentorTeams.mockResolvedValue(fixtures.teams);
  api.fetchMentorTeam.mockResolvedValue(fixtures.teamDetail);
  api.fetchMentorNotes.mockResolvedValue(fixtures.notes);
  api.fetchMentorNotices.mockResolvedValue(fixtures.notices);
  api.fetchMentorBoard.mockResolvedValue(fixtures.board);
});

describe("mentor shell", () => {
  it("lists every console section and the teacher hop for dual-role staff", () => {
    render(<MentorShell><p>body</p></MentorShell>);
    for (const label of ["Dashboard", "My mentees", "At-risk alerts", "Mentoring log", "Project teams", "Classes", "Notices", "Teacher console"]) {
      expect(screen.getAllByRole("link", { name: new RegExp(label) }).length).toBeGreaterThan(0);
    }
  });
});

describe("mentor console pages", () => {
  it("dashboard shows scope counts, at-risk mentees and upcoming scope", async () => {
    render(<MentorDashboardPage />);
    expect(await screen.findByText(/Welcome, Tina/)).toBeInTheDocument();
    expect(screen.getAllByText("Mentees")[0]!.nextElementSibling).toHaveTextContent(String(fixtures.dashboard.mentee_count));
    expect(screen.getByText(/Attendance below 75%/)).toBeInTheDocument();
    expect(screen.getAllByText("Student Two").length).toBeGreaterThan(0); // at-risk list
    expect(screen.getByText("Team Rocket")).toBeInTheDocument();
    expect(screen.getByText("CSE-A")).toBeInTheDocument();
  });

  it("mentee directory renders every row with scope chips and attendance", async () => {
    render(<MentorMenteesPage />);
    expect(await screen.findByText(`${fixtures.mentees.total} students`)).toBeInTheDocument();
    for (const row of fixtures.mentees.items) expect(screen.getByText(row.student_name)).toBeInTheDocument();
    expect(screen.getAllByText("Direct mentee").length).toBeGreaterThan(0);
    expect(screen.getAllByText("50%").length).toBeGreaterThan(0);
    expect(api.fetchMentorMentees).toHaveBeenCalledWith(expect.objectContaining({ atRisk: false }));
  });

  it("at-risk alerts page requests only flagged mentees", async () => {
    render(<MentorMenteesPage atRiskOnly />);
    expect(await screen.findByRole("heading", { name: "At-risk alerts" })).toBeInTheDocument();
    expect(api.fetchMentorMentees).toHaveBeenCalledWith(expect.objectContaining({ atRisk: true }));
  });

  it("mentee profile shows attendance, subjects, guardians and lets the mentor log a note", async () => {
    api.createMentorNote.mockResolvedValue({
      ...fixtures.notes.items[0],
      id: "new-note",
      body: "Met after class; agreed on a study plan.",
      is_private: true,
      note_date: "2026-09-24",
      created_at: "2026-09-24T10:00:00Z",
      updated_at: "2026-09-24T10:00:00Z",
    });
    render(<MentorMenteeDetailPage studentId={STUDENT_TWO} />);
    expect(await screen.findByRole("heading", { name: "Student Two" })).toBeInTheDocument();
    expect(screen.getByText("Attendance by subject")).toBeInTheDocument();
    expect(screen.getByText("Data Structures")).toBeInTheDocument();
    expect(screen.getAllByText("Present")[0]!.nextElementSibling).toHaveTextContent("2");
    expect(screen.getAllByText("Absent")[0]!.nextElementSibling).toHaveTextContent("2");

    fireEvent.change(screen.getByLabelText(/Log a conversation/), { target: { value: "Met after class; agreed on a study plan." } });
    fireEvent.click(screen.getByRole("button", { name: /Save note/ }));
    await waitFor(() => expect(api.createMentorNote).toHaveBeenCalledWith(STUDENT_TWO, expect.objectContaining({ body: "Met after class; agreed on a study plan.", is_private: true })));
    expect(await screen.findByText("Met after class; agreed on a study plan.")).toBeInTheDocument();
  });

  it("mentoring log supports inline edit and delete of own notes", async () => {
    const note = fixtures.notes.items[0];
    api.updateMentorNote.mockResolvedValue({ ...note, body: "Edited in log", is_private: false });
    api.deleteMentorNote.mockResolvedValue(null);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<MentorNotesPage />);
    expect(await screen.findByText(note.body)).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText("Edit note"));
    fireEvent.change(screen.getByLabelText("Note text"), { target: { value: "Edited in log" } });
    fireEvent.click(screen.getByRole("button", { name: /^Save$/ }));
    await waitFor(() => expect(api.updateMentorNote).toHaveBeenCalledWith(note.id, expect.objectContaining({ body: "Edited in log" })));
    expect(await screen.findByText("Edited in log")).toBeInTheDocument();

    fireEvent.click(screen.getByLabelText("Delete note"));
    await waitFor(() => expect(api.deleteMentorNote).toHaveBeenCalledWith(note.id));
    await waitFor(() => expect(screen.queryByText("Edited in log")).not.toBeInTheDocument());
  });

  it("classes page renders roster size, at-risk count and class teacher", async () => {
    render(<MentorClassesPage />);
    expect(await screen.findByText("CSE-A")).toBeInTheDocument();
    expect(screen.getByText("1 at risk")).toBeInTheDocument();
    expect(screen.getByText("Tina Teacher")).toBeInTheDocument();
  });

  it("teams list and team workspace render members, tasks and chat", async () => {
    const { unmount } = render(<MentorTeamsPage />);
    expect(await screen.findByText("Team Rocket")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open team" })).toHaveAttribute("href", `/mentor/teams/${TEAM}`);
    unmount();

    render(<MentorTeamDetailPage teamId={TEAM} />);
    expect(await screen.findByRole("heading", { name: "Team Rocket" })).toBeInTheDocument();
    expect(screen.getByText(/Members \(2\)/)).toBeInTheDocument();
    expect(screen.getByText("Write proposal")).toBeInTheDocument();
    expect(screen.getByText("Hello team")).toBeInTheDocument();
  });

  it("notice board is read-only for mentors and lists visible notices", async () => {
    render(<MentorNoticesPage />);
    expect(await screen.findByText("Welcome back")).toBeInTheDocument();
    expect(screen.getByText("CSE-B only")).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: /Post notice/ })).not.toBeInTheDocument();
  });
});

describe("coordinator / admin allocation board", () => {
  it("renders coverage, mentors and submits a class assignment", async () => {
    api.assignMentor.mockResolvedValue(fixtures.board);
    render(<MentorAssignmentsBoardPage />);
    expect(await screen.findByText("Classes with a mentor")).toBeInTheDocument();
    expect(screen.getByText("Mentors and their scope")).toBeInTheDocument();
    for (const mentor of fixtures.board.mentors) expect(screen.getByRole("heading", { name: new RegExp(mentor.mentor_name) })).toBeInTheDocument();

    const target = fixtures.board.classes[0];
    const mentor = fixtures.board.candidates[0];
    fireEvent.change(screen.getByLabelText("Assign to"), { target: { value: "CLASS" } });
    fireEvent.change(screen.getByLabelText("Class"), { target: { value: target.id } });
    fireEvent.change(screen.getByLabelText("Mentor"), { target: { value: mentor.id } });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    fireEvent.click(screen.getByRole("button", { name: /assign mentor/i }));
    await waitFor(() => expect(api.assignMentor).toHaveBeenCalledWith({ mentor_id: mentor.id, scope_type: "CLASS", target_id: target.id, notes: null }));
  });

  it("removes an assignment through the API and shows the admin fallback copy", async () => {
    api.removeMentorAssignment.mockResolvedValue({ ...fixtures.board, mentors: [] });
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<MentorAssignmentsBoardPage isAdmin />);
    expect(await screen.findByText(/Operational fallback/)).toBeInTheDocument();
    const first = fixtures.board.mentors[0].assignments[0];
    fireEvent.click(screen.getByRole("button", { name: `Remove ${first.target_name} from ${fixtures.board.mentors[0].mentor_name}` }));
    await waitFor(() => expect(api.removeMentorAssignment).toHaveBeenCalledWith(first.id));
    expect(await screen.findByText(/No mentor assignments yet/)).toBeInTheDocument();
  });
});

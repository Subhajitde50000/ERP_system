import { MentorAssignmentsBoardPage } from "@/components/mentor/mentor-assignments-board";

/** Institution Admin — operational fallback for mentor allocation. */
export default function AdminMentorsRoute() { return <MentorAssignmentsBoardPage isAdmin />; }

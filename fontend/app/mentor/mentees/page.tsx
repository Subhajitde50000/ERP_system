"use client";

import { use } from "react";

import { MentorMenteesPage } from "@/components/mentor/mentor-mentees";

export default function MentorMenteesRoute({ searchParams }: { searchParams: Promise<{ class?: string }> }) {
  const { class: classId } = use(searchParams);
  return <MentorMenteesPage initialClassId={classId ?? ""} />;
}

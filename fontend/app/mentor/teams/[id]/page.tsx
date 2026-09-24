"use client";

import { use } from "react";

import { MentorTeamDetailPage } from "@/components/mentor/mentor-teams";

export default function MentorTeamRoute({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return <MentorTeamDetailPage teamId={id} />;
}

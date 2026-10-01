"use client";

import { use } from "react";

import { MentorMenteeDetailPage } from "@/components/mentor/mentor-mentee-detail";

export default function MentorMenteeRoute({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  return <MentorMenteeDetailPage studentId={id} />;
}

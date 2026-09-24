"use client";

import { LeadershipNoticesPage, type LeadershipNoticesConfig } from "@/components/principal/notices";
import { fetchMentorNotice, fetchMentorNotices } from "@/lib/mentor";

/** Read-only board: institution notices plus those aimed at mentees' departments and classes. */
const CONFIG: LeadershipNoticesConfig = {
  title: "Notice board",
  subtitle: "Institution notices and those addressed to your mentees' departments and classes.",
  canViewReadReceipts: false,
  canPin: false,
  allowedPostScopes: [],
  load: (filters) => fetchMentorNotices({ query: filters.query, scope: filters.scope, limit: filters.limit, offset: filters.offset }),
  loadDetail: fetchMentorNotice,
  loadTargets: async () => ({ departments: [], classes: [] }),
  create: async () => {
    throw new Error("Mentors read notices; posting is done from the teacher or leadership consoles.");
  },
};

export function MentorNoticesPage() {
  return <LeadershipNoticesPage config={CONFIG} />;
}

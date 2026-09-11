import type { Metadata } from "next";

import { LandingPage } from "@/components/marketing/landing-page";

export const metadata: Metadata = {
  title: "Connected operations for education institutions",
  description:
    "Explore shikshasync.me, the connected ERP and learning platform for schools, colleges and universities.",
  robots: { index: true, follow: true },
};

/** Public root domain: explore the platform and request a sales consultation. */
export default function Home() {
  return <LandingPage />;
}

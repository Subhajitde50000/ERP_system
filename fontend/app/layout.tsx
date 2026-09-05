import type { Metadata, Viewport } from "next";
import "./globals.css";

/*
 * Typography is defined as local/system stacks in globals.css.  Keeping fonts
 * local means a production build and first render do not depend on Google
 * Fonts being reachable from the build environment or a school network.
 */

export const metadata: Metadata = {
  metadataBase: new URL(process.env.NEXT_PUBLIC_APP_URL || "https://xyz.com"),
  title: {
    default: "xyz.com · Education, connected",
    template: "%s · xyz.com",
  },
  description:
    "Secure, multi-tenant ERP + LMS for schools and colleges. Attendance, exams, assignments, fees, hostel and more.",
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      "max-video-preview": -1,
      "max-image-preview": "large",
      "max-snippet": -1,
    },
  },
  openGraph: {
    title: "xyz.com · Education, connected",
    description:
      "Secure, multi-tenant ERP + LMS for schools and colleges. Attendance, exams, assignments, fees, hostel and more.",
    url: "https://xyz.com",
    siteName: "xyz.com",
    locale: "en_IN",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "xyz.com · Education, connected",
    description:
      "Secure, multi-tenant ERP + LMS for schools and colleges. Attendance, exams, assignments, fees, hostel and more.",
  },
};

export const viewport: Viewport = {
  themeColor: "#0F172A",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-background font-sans text-foreground antialiased">
        {children}
      </body>
    </html>
  );
}

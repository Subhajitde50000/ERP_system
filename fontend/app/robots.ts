import type { MetadataRoute } from "next";

/**
 * Next.js App Router Robots metadata route.
 * Automatically generates /robots.txt to permit indexing of public marketing,
 * product, pricing, and compliance routes, while strictly disallowing private
 * institution consoles, platform administration, and internal API routes.
 */
export default function robots(): MetadataRoute.Robots {
  const baseUrl = process.env.NEXT_PUBLIC_APP_URL || "https://xyz.com";

  return {
    rules: [
      {
        userAgent: "*",
        allow: [
          "/",
          "/features",
          "/pricing",
          "/solutions",
          "/security",
          "/customers",
          "/about",
          "/faq",
          "/contact",
          "/signup",
          "/privacy",
          "/terms",
          "/refund-policy",
        ],
        disallow: [
          "/admin/",
          "/platform/",
          "/account/",
          "/student/",
          "/teacher/",
          "/parent/",
          "/principal/",
          "/vp/",
          "/hod/",
          "/coordinator/",
          "/exam-controller/",
          "/librarian/",
          "/hostel-warden/",
          "/api/",
          "/forgot-password",
          "/verify-email",
          "/reset-password",
          "/guardian-access",
        ],
      },
    ],
    sitemap: `${baseUrl}/sitemap.xml`,
  };
}

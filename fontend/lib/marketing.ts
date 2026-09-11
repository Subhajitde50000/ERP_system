/**
 * Marketing content — the single source of truth shared by every public page
 * (landing, features, solutions, security, customers, about, contact, faq).
 * Keeps module copy, audiences, testimonials and FAQ consistent so the site
 * never drifts, and lets pages reference the same data instead of duplicating
 * it.
 */

import {
  Award,
  BookOpenCheck,
  Briefcase,
  Building2,
  Bus,
  CalendarClock,
  CalendarCheck2,
  ClipboardCheck,
  CreditCard,
  FileText,
  GraduationCap,
  Library,
  Megaphone,
  MessageSquare,
  Package,
  ShieldCheck,
  Users,
  UserPlus,
  Wallet,
  type LucideIcon,
} from "lucide-react";

export interface ModuleCard {
  key: string;
  name: string;
  category: "Core" | "Optional";
  blurb: string;
  icon: LucideIcon;
}

/** The real 16 modules — 8 core (always on) + 8 optional (per plan). */
export const MODULES: ModuleCard[] = [
  { key: "attendance", name: "Attendance", category: "Core", blurb: "Self, class, parent and exam-hall attendance with real-time shortfall alerts.", icon: ClipboardCheck },
  { key: "examination", name: "Examinations", category: "Core", blurb: "Scheduling, hall management, online attempts, malpractice tracking and results.", icon: FileText },
  { key: "assignment", name: "Assignments", category: "Core", blurb: "Milestone-based coursework, submissions, reviews and parent visibility.", icon: BookOpenCheck },
  { key: "notice", name: "Notices", category: "Core", blurb: "Targeted announcements with read-receipts across staff, students and families.", icon: Megaphone },
  { key: "discussion", name: "Discussions", category: "Core", blurb: "Threaded class and subject conversations that stay tied to the course.", icon: MessageSquare },
  { key: "content", name: "Content & LMS", category: "Core", blurb: "A structured library for lessons, resources and e-content delivery.", icon: Library },
  { key: "results", name: "Results", category: "Core", blurb: "Subject-wise marks, GPA/CGPA, publications and parent result views.", icon: Award },
  { key: "timetable", category: "Core", name: "Timetable", blurb: "Conflict-aware scheduling for classes, teachers, rooms and substitutions.", icon: CalendarClock },

  { key: "finance", name: "Finance & Fees", category: "Optional", blurb: "Fee structures, instalments, online collection, defaulters and scholarships.", icon: Wallet },
  { key: "admission", name: "Admissions", category: "Optional", blurb: "Cycles, online applications, merit lists and enrolment workflows.", icon: UserPlus },
  { key: "hr", name: "HR & Payroll", category: "Optional", blurb: "Staff records, leave, attendance-linked payroll and appraisals.", icon: Users },
  { key: "library", name: "Library", category: "Optional", blurb: "Catalogue, circulation, reservations, e-resources and overdue tracking.", icon: BookOpenCheck },
  { key: "hostel", name: "Hostel", category: "Optional", blurb: "Blocks, rooms, allotments, occupancy and warden workflows.", icon: Building2 },
  { key: "transport", name: "Transport", category: "Optional", blurb: "Routes, stops, vehicles, passes and live pickup tracking.", icon: Bus },
  { key: "placement", name: "Placement", category: "Optional", blurb: "Companies, drives, offers and placement analytics for colleges.", icon: Briefcase },
  { key: "inventory", name: "Inventory", category: "Optional", blurb: "Stock, vendors, purchase orders and consumption for labs and stores.", icon: Package },
];

export interface Audience {
  slug: "schools" | "colleges" | "universities" | "multi-campus";
  title: string;
  tagline: string;
  description: string;
  highlights: string[];
  icon: LucideIcon;
}

export const AUDIENCES: Audience[] = [
  {
    slug: "schools",
    title: "For Schools",
    tagline: "K–12, made simple",
    description:
      "Parent links, roll-number logins, class teachers and exam halls — designed for the rhythms of a school day and the families it serves.",
    highlights: ["Parent & student portals", "House exams and report cards", "Fee reminders to families", "Transport and hostel add-ons"],
    icon: GraduationCap,
  },
  {
    slug: "colleges",
    title: "For Colleges",
    tagline: "Departments to degrees",
    description:
      "Department, HOD and programme structure with CGPA results, placements and accreditation-ready records.",
    highlights: ["Department & programme hierarchy", "Semester results and CGPA", "Placement cell", "Library and HR"],
    icon: BookOpenCheck,
  },
  {
    slug: "universities",
    title: "For Universities",
    tagline: "Govern at scale",
    description:
      "Multi-faculty governance, unified finance and reporting across affiliated and constituent units.",
    highlights: ["Multi-campus governance", "Centralised finance", "Audit and reporting", "Enterprise SLAs"],
    icon: Building2,
  },
  {
    slug: "multi-campus",
    title: "Multi-Campus Groups",
    tagline: "One account, many institutions",
    description:
      "Own several institutions under a single platform account — consolidated billing, subscriptions and support.",
    highlights: ["One login, many campuses", "Consolidated billing", "Cross-campus support", "Central administration"],
    icon: Building2,
  },
];

export interface Stat {
  value: string;
  label: string;
}

export const STATS: Stat[] = [
  { value: "500+", label: "Institutions" },
  { value: "1.2M+", label: "Learners managed" },
  { value: "16", label: "Modules, one platform" },
  { value: "99.95%", label: "Uptime over 12 months" },
];

export interface Testimonial {
  quote: string;
  name: string;
  role: string;
  org: string;
}

export const TESTIMONIALS: Testimonial[] = [
  {
    quote:
      "Attendance that used to take every teacher 15 minutes now takes seconds, and parents see the absence before the child is even home.",
    name: "Dr. Meera Iyer",
    role: "Principal",
    org: "Greenwood International School",
  },
  {
    quote:
      "We rolled out exams, fees and results in a single term. The role-based workspaces meant every department adopted it without training.",
    name: "Prof. Anand Rao",
    role: "Vice Principal",
    org: "Northstar College of Engineering",
  },
  {
    quote:
      "One account manages all three of our campuses. Consolidated billing and a single support contact saved us weeks every quarter.",
    name: "Rahul Sharma",
    role: "Director",
    org: "Sharma Education Trust",
  },
];

export interface Faq {
  q: string;
  a: string;
}

export const FAQS: Faq[] = [
  {
    q: "How is shikshasync.me different from a generic school management tool?",
    a: "It is a true multi-tenant platform: one account can own many institutions, each with its own subdomain, data isolation, roles and billing. Eight core academic modules come included, and you switch on optional modules as you grow.",
  },
  {
    q: "Do you support self-service signup?",
    a: "Yes. Create a platform account, verify your email, then spin up an institution with a plan and subdomain. Provisioning is automatic — your tenant, admin user, modules and academic-year template are ready before you finish your coffee.",
  },
  {
    q: "Can one person manage multiple institutions?",
    a: "That is the whole point. A single platform account owns every institution you run, with consolidated subscriptions, invoices and support tickets in one dashboard.",
  },
  {
    q: "How long does implementation take?",
    a: "A single institution is live in minutes through self-service. Larger rollouts are guided by our team and phased around your academic calendar — departments, classes and bulk student import come next.",
  },
  {
    q: "Is our data isolated from other institutions?",
    a: "Completely. Every institution is a separate tenant with isolated data, its own roles and a JWT bound to its origin. A token from one institution cannot be replayed against another.",
  },
  {
    q: "How does pricing work?",
    a: "Pick a plan (Starter, Professional or Enterprise) or build your own from individual modules. Monthly or yearly billing, GST-compliant invoicing, and a 14-day free trial with no card required.",
  },
];

export interface NavItem {
  label: string;
  href: string;
}

export const PRIMARY_NAV: NavItem[] = [
  { label: "Features", href: "/features" },
  { label: "Solutions", href: "/solutions" },
  { label: "Security", href: "/security" },
  { label: "Customers", href: "/customers" },
  { label: "Pricing", href: "/pricing" },
  { label: "About", href: "/about" },
];

export interface SecurityPoint {
  title: string;
  description: string;
  icon: LucideIcon;
}

export const SECURITY_POINTS: SecurityPoint[] = [
  { title: "Tenant data isolation", description: "Every institution is a separate tenant. Row-level isolation and origin-bound tokens keep data from ever crossing institutions.", icon: ShieldCheck },
  { title: "Role-based access control", description: "18 fine-grained institution roles with module.action.scope permissions. People see only what their role grants.", icon: Users },
  { title: "Encrypted credentials", description: "Passwords are bcrypt-hashed at cost 12. Refresh tokens are SHA-256 hashed at rest; access tokens never touch storage.", icon: ShieldCheck },
  { title: "Audit & traceability", description: "Every privileged action is recorded in audit logs with the actor, time and request id — for compliance and incident review.", icon: FileText },
  { title: "GST-compliant billing", description: "Gapless invoice numbering, CGST/SGST/IGST split by place of supply, and idempotent payment records.", icon: CreditCard },
  { title: "99.95% uptime", description: "Health-checked infrastructure with graceful degradation — a school mid-term still sees today's timetable while finance resolves a payment.", icon: CalendarCheck2 },
];

# ERP + LMS Platform — Complete Webpage Inventory & Developer Assignment

> All pages across every role · Platform + Institution layers  
> Total Pages: 187 pages  
> Developer C owns all frontend pages  
> Developer A owns all backend APIs feeding those pages  
> Developer B owns all module-specific backend APIs  

---

## Table of Contents

1. [Page Count Summary](#1-page-count-summary)
2. [Platform Layer Pages — Super Admin, Support, Sales, Finance](#2-platform-layer-pages)
3. [Institution Layer — Institution Admin](#3-institution-admin-pages)
4. [Institution Layer — Principal & Vice Principal](#4-principal--vice-principal-pages)
5. [Institution Layer — HOD](#5-hod-pages)
6. [Institution Layer — Teacher](#6-teacher-pages)
7. [Institution Layer — Exam Controller](#7-exam-controller-pages)
8. [Institution Layer — Academic Coordinator](#8-academic-coordinator-pages)
9. [Institution Layer — Accountant](#9-accountant-pages)
10. [Institution Layer — Student](#10-student-pages)
11. [Institution Layer — Parent (School only)](#11-parent-pages)
12. [Optional Module — Librarian](#12-librarian-pages)
13. [Optional Module — Hostel Warden](#13-hostel-warden-pages)
14. [Optional Module — Transport Manager](#14-transport-manager-pages)
15. [Optional Module — Placement Officer](#15-placement-officer-pages)
16. [Optional Module — HR Manager](#16-hr-manager-pages)
17. [Optional Module — Admission Officer](#17-admission-officer-pages)
18. [Optional Module — Store Manager](#18-store-manager-pages)
19. [Shared / Public Pages](#19-shared--public-pages)
20. [Full Master Page Table](#20-full-master-page-table)

---

## 1. Page Count Summary

| Layer | Role | Pages | Dev (Backend) | Dev (Frontend) |
|---|---|---|---|---|
| Platform | Super Admin | 8 | Dev-A | Dev-C |
| Platform | Support Staff | 4 | Dev-A | Dev-C |
| Platform | Sales Executive | 4 | Dev-A | Dev-C |
| Platform | Finance Manager | 4 | Dev-A | Dev-C |
| Institution | Institution Admin | 18 | Dev-A | Dev-C |
| Institution | Principal | 10 | Dev-A + Dev-B | Dev-C |
| Institution | Vice Principal | 7 | Dev-A + Dev-B | Dev-C |
| Institution | HOD | 12 | Dev-B | Dev-C |
| Institution | Teacher | 22 | Dev-B | Dev-C |
| Institution | Exam Controller | 10 | Dev-B | Dev-C |
| Institution | Academic Coordinator | 8 | Dev-B | Dev-C |
| Institution | Accountant | 10 | Dev-B | Dev-C |
| Institution | Student | 20 | Dev-B | Dev-C |
| Institution | Parent (School) | 8 | Dev-B | Dev-C |
| Optional | Librarian | 8 | Dev-B | Dev-C |
| Optional | Hostel Warden | 8 | Dev-B | Dev-C |
| Optional | Transport Manager | 6 | Dev-B | Dev-C |
| Optional | Placement Officer | 10 | Dev-B | Dev-C |
| Optional | HR Manager | 12 | Dev-B | Dev-C |
| Optional | Admission Officer | 8 | Dev-B | Dev-C |
| Optional | Store Manager | 8 | Dev-B | Dev-C |
| Shared | Auth / Public | 6 | Dev-A | Dev-C |
| **TOTAL** | | **187 pages** | | |

---

## 2. Platform Layer Pages

> These pages live at `app.shikshasync.me` — not institution subdomains  
> Backend: **Dev-A** | Frontend: **Dev-C**  
> Next.js route prefix: `app/(platform)/`

### 2.1 Super Admin (8 pages)

| # | Page Name | Route | Description | Task ID |
|---|---|---|---|---|
| 1 | Super Admin Dashboard | `/dashboard` | KPIs: total institutions, active users, revenue, tickets | C-SA-01 |
| 2 | Institution List | `/institutions` | All tenants table: name, plan, status, student count | C-SA-02 |
| 3 | Institution Detail | `/institutions/:id` | View/edit one institution profile + plan + modules enabled | C-SA-03 |
| 4 | Create Institution | `/institutions/new` | Form: name, slug, type (school/college), plan, admin email | C-SA-04 |
| 5 | Subscription & Plans | `/plans` | Manage plans (Basic/Standard/Premium), pricing, features | C-SA-05 |
| 6 | Platform Users | `/platform-users` | Manage Support/Sales/Finance staff accounts | C-SA-06 |
| 7 | Audit Logs Viewer | `/audit-logs` | Global audit trail: filter by tenant, user, action, date | C-SA-07 |
| 8 | Platform Settings | `/settings` | Global config: allowed modules list, platform branding | C-SA-08 |

**Backend APIs (Dev-A):**
- `GET/POST/PATCH/DELETE /api/v1/platform/tenants`
- `GET/POST/PATCH /api/v1/platform/plans`
- `GET/POST/PATCH /api/v1/platform/users`
- `GET /api/v1/platform/audit-logs`
- `GET /api/v1/platform/dashboard-stats`

---

### 2.2 Support Staff (4 pages)

| # | Page Name | Route | Description | Task ID |
|---|---|---|---|---|
| 9 | Support Dashboard | `/support/dashboard` | Open tickets count, priority breakdown, assigned to me | C-SP-01 |
| 10 | Ticket List | `/support/tickets` | All tickets: filter by status, priority, institution | C-SP-02 |
| 11 | Ticket Detail | `/support/tickets/:id` | View ticket + reply thread + change status | C-SP-03 |
| 12 | Institution Read-Only View | `/support/institutions/:id` | Read-only audit-mode view of any institution's data | C-SP-04 |

**Backend APIs (Dev-A):**
- `GET/PATCH /api/v1/platform/tickets`
- `GET /api/v1/platform/tickets/:id`
- `POST /api/v1/platform/tickets/:id/reply`
- `GET /api/v1/platform/institutions/:id/readonly`

---

### 2.3 Sales Executive (4 pages)

| # | Page Name | Route | Description | Task ID |
|---|---|---|---|---|
| 13 | Sales Dashboard | `/sales/dashboard` | Trial institutions, conversion rate, recent signups | C-SL-01 |
| 14 | Lead / Trial Institutions | `/sales/trials` | All trial tenants: days left, contact, follow-up notes | C-SL-02 |
| 15 | Convert Trial to Paid | `/sales/trials/:id/convert` | Select plan, set billing start, send welcome email | C-SL-03 |
| 16 | Subscription Management | `/sales/subscriptions` | All active subscriptions: renew, upgrade, downgrade | C-SL-04 |

**Backend APIs (Dev-A):**
- `GET /api/v1/platform/trials`
- `POST /api/v1/platform/trials/:id/convert`
- `GET/PATCH /api/v1/platform/subscriptions`

---

### 2.4 Finance Manager (4 pages)

| # | Page Name | Route | Description | Task ID |
|---|---|---|---|---|
| 17 | Finance Dashboard | `/finance/dashboard` | Monthly revenue, unpaid invoices, MRR chart | C-FM-01 |
| 18 | Invoices | `/finance/invoices` | All invoices: paid/unpaid/overdue, download PDF | C-FM-02 |
| 19 | Payment Records | `/finance/payments` | Transaction history across all institutions | C-FM-03 |
| 20 | Revenue Reports | `/finance/reports` | Monthly/yearly revenue breakdown by plan, export CSV | C-FM-04 |

**Backend APIs (Dev-A):**
- `GET /api/v1/platform/finance/dashboard`
- `GET /api/v1/platform/invoices`
- `GET /api/v1/platform/payments`
- `GET /api/v1/platform/finance/reports`

---

## 3. Institution Admin Pages

> Route prefix: `[slug].shikshasync.me` → `app/(institution)/admin/`  
> Backend: **Dev-A** (structure APIs) + **Dev-B** (module APIs)  
> Frontend: **Dev-C**

| # | Page Name | Route | Description | Task ID |
|---|---|---|---|---|
| 21 | Admin Dashboard | `/dashboard` | Institution overview: total students, staff, active modules, recent activity | C-IA-01 |
| 22 | Department Management | `/departments` | List, create, edit, delete departments. Assign HOD. | C-IA-02 |
| 23 | Department Detail | `/departments/:id` | Dept info, HOD, class list, subject list | C-IA-03 |
| 24 | Academic Year Setup | `/academic-years` | Create years, set current year, view archive | C-IA-04 |
| 25 | Class Management | `/classes` | All classes: filter by dept, year. Create/edit/delete. | C-IA-05 |
| 26 | Class Detail | `/classes/:id` | Students enrolled, subjects, class teacher, timetable | C-IA-06 |
| 27 | Subject Management | `/subjects` | All subjects by class. Assign teachers. | C-IA-07 |
| 28 | User Management | `/users` | All users: filter by role. Invite, deactivate, reset password. | C-IA-08 |
| 29 | User Detail / Profile | `/users/:id` | Full profile, roles assigned, activity log | C-IA-09 |
| 30 | Role Assignment | `/users/:id/roles` | Assign/revoke roles scoped to dept/class/subject | C-IA-10 |
| 31 | Student Enrollment | `/enrollments` | Bulk enroll students into class for academic year | C-IA-11 |
| 32 | Parent–Student Links | `/parent-links` | Link parent accounts to student (school only) | C-IA-12 |
| 33 | Settings — General | `/settings/general` | Institution name, logo, timezone, contact info | C-IA-13 |
| 34 | Settings — Modules | `/settings/modules` | **THE module toggle page** — enable/disable optional modules | C-IA-14 |
| 35 | Settings — Fee Structure | `/settings/fees` | Define fee heads per academic year (links to Accountant) | C-IA-15 |
| 36 | Settings — Notifications | `/settings/notifications` | Configure which events trigger push/email/SMS | C-IA-16 |
| 37 | Support Tickets | `/support` | Raise + track tickets with platform support team | C-IA-17 |
| 38 | Audit Logs | `/audit-logs` | Institution-level audit trail of all admin actions | C-IA-18 |

**Backend APIs:**
- Dev-A: departments, classes, subjects, users, roles, enrollments, settings, audit
- Dev-B: fee structure (B-113), module toggle feeds notification config

---

## 4. Principal & Vice Principal Pages

> Backend: Dev-A (structure) + Dev-B (module analytics)  
> Frontend: **Dev-C**

### Principal (10 pages)

| # | Page Name | Route | Description | Task ID |
|---|---|---|---|---|
| 39 | Principal Dashboard | `/principal/dashboard` | Institution-wide: attendance %, results summary, notice board, upcoming exams | C-PR-01 |
| 40 | Attendance Overview | `/principal/attendance` | All departments attendance % — heatmap by dept/class | C-PR-02 |
| 41 | Exam Schedule View | `/principal/examinations` | All upcoming/ongoing/completed exams across institution | C-PR-03 |
| 42 | Results Overview | `/principal/results` | Class-wise and dept-wise result summary with pass % | C-PR-04 |
| 43 | Staff Directory | `/principal/staff` | All teachers, HODs, coordinators — view profiles | C-PR-05 |
| 44 | Student Directory | `/principal/students` | All students — view profiles, class, enrollment status | C-PR-06 |
| 45 | Notice Board | `/principal/notices` | View all notices + compose institution-wide notice | C-PR-07 |
| 46 | Post Notice | `/principal/notices/new` | Compose and publish institution-wide or dept notice | C-PR-08 |
| 47 | Timetable View | `/principal/timetable` | View any class timetable | C-PR-09 |
| 48 | Reports | `/principal/reports` | Export attendance, result, and performance reports | C-PR-10 |

### Vice Principal (7 pages)

| # | Page Name | Route | Description | Task ID |
|---|---|---|---|---|
| 49 | VP Dashboard | `/vp/dashboard` | Same as Principal but with delegated dept scope | C-VP-01 |
| 50 | Attendance Report | `/vp/attendance` | Dept attendance overview | C-VP-02 |
| 51 | Exam Schedule View | `/vp/examinations` | View exam schedule | C-VP-03 |
| 52 | Results View | `/vp/results` | View results (read-only, cannot approve) | C-VP-04 |
| 53 | Notice Board | `/vp/notices` | View + compose dept/class notices | C-VP-05 |
| 54 | Post Notice | `/vp/notices/new` | Compose notice | C-VP-06 |
| 55 | Staff Directory | `/vp/staff` | View staff profiles | C-VP-07 |

---

## 5. HOD Pages

> Backend: **Dev-B** | Frontend: **Dev-C**

| # | Page Name | Route | Description | Task ID |
|---|---|---|---|---|
| 56 | HOD Dashboard | `/hod/dashboard` | Dept KPIs: attendance %, results, assignments pending, notices | C-HD-01 |
| 57 | Department Attendance | `/hod/attendance` | Class-wise attendance heatmap for own dept | C-HD-02 |
| 58 | Attendance Report Detail | `/hod/attendance/report` | Per-student per-subject attendance, export CSV | C-HD-03 |
| 59 | Exam List (Dept) | `/hod/examinations` | All exams in dept — view schedules + results | C-HD-04 |
| 60 | Assignment Overview | `/hod/assignments` | All assignments across dept — pending reviews count | C-HD-05 |
| 61 | Results Overview (Dept) | `/hod/results` | Class-wise results in own dept | C-HD-06 |
| 62 | Teacher List | `/hod/teachers` | Teachers in own dept — assign to subjects | C-HD-07 |
| 63 | Mentor Assignments | `/hod/mentors` | Assign students to mentors (if Mentor role enabled) | C-HD-08 |
| 64 | Notice Board | `/hod/notices` | View all + post dept-level notices | C-HD-09 |
| 65 | Post Notice | `/hod/notices/new` | Compose dept or class notice | C-HD-10 |
| 66 | Discussion Moderation | `/hod/discussion` | View dept threads, pin/lock/delete as moderator | C-HD-11 |
| 67 | Timetable View | `/hod/timetable` | View all class timetables in own dept | C-HD-12 |

---

## 6. Teacher Pages

> Backend: **Dev-B** | Frontend: **Dev-C**  
> Teachers see data scoped to their assigned subjects/classes only

| # | Page Name | Route | Description | Task ID |
|---|---|---|---|---|
| 68 | Teacher Dashboard | `/teacher/dashboard` | Today's classes, pending submissions, upcoming exams, recent notices | C-TC-01 |
| 69 | My Schedule | `/teacher/schedule` | Weekly timetable view for own subjects | C-TC-02 |
| 70 | Mark Attendance | `/teacher/attendance/mark` | Select class + subject + date → mark P/A/L per student | C-TC-03 |
| 71 | Attendance Sessions | `/teacher/attendance/sessions` | List of all sessions marked, filter by date/class/subject | C-TC-04 |
| 72 | Session Detail | `/teacher/attendance/sessions/:id` | View/edit individual session records (before lock) | C-TC-05 |
| 73 | Leave Requests | `/teacher/attendance/leaves` | Review student leave applications for own classes | C-TC-06 |
| 74 | Exam List | `/teacher/examinations` | All exams created by this teacher — filter by status | C-TC-07 |
| 75 | Create Exam | `/teacher/examinations/new` | Form: title, subject, class, type, duration, schedule | C-TC-08 |
| 76 | Exam Detail / Edit | `/teacher/examinations/:id` | Edit draft exam, add questions, preview | C-TC-09 |
| 77 | Add Questions | `/teacher/examinations/:id/questions` | Add MCQ, descriptive, true/false questions + options | C-TC-10 |
| 78 | Exam Results | `/teacher/examinations/:id/results` | Submission list, grade descriptive answers, release results | C-TC-11 |
| 79 | Assignment List | `/teacher/assignments` | All assignments created by teacher | C-TC-12 |
| 80 | Create Assignment | `/teacher/assignments/new` | Form: title, subject, due date, type (regular/milestone) | C-TC-13 |
| 81 | Assignment Detail | `/teacher/assignments/:id` | Edit assignment, add milestones, view submissions | C-TC-14 |
| 82 | Submission Review | `/teacher/assignments/:id/submissions` | All student submissions — approve/reject/request resubmit | C-TC-15 |
| 83 | Submission Detail | `/teacher/submissions/:id` | View one submission, files, add feedback, set score | C-TC-16 |
| 84 | Content Upload | `/teacher/content` | List of uploaded notes/videos/slides per subject | C-TC-17 |
| 85 | Upload Content | `/teacher/content/upload` | Upload file (PDF/video/slide) or add link, tag by chapter | C-TC-18 |
| 86 | Notice Board | `/teacher/notices` | View all notices + post class-level notice | C-TC-19 |
| 87 | Post Notice | `/teacher/notices/new` | Compose notice scoped to own class | C-TC-20 |
| 88 | Discussion Forum | `/teacher/discussion` | View threads in own subjects, post, reply, mark answer | C-TC-21 |
| 89 | Thread Detail | `/teacher/discussion/:id` | Replies, accept answer, lock/pin thread | C-TC-22 |

---

## 7. Exam Controller Pages

> Backend: **Dev-B** | Frontend: **Dev-C**

| # | Page Name | Route | Description | Task ID |
|---|---|---|---|---|
| 90 | Exam Controller Dashboard | `/exam-controller/dashboard` | All exams by status, pending grading count, upcoming schedule | C-EC-01 |
| 91 | Exam Schedule | `/exam-controller/schedule` | Institution-wide exam timetable — all depts, all classes | C-EC-02 |
| 92 | Create / Edit Exam Schedule | `/exam-controller/schedule/new` | Schedule exam date/time/hall for any class | C-EC-03 |
| 93 | Hall Allocation | `/exam-controller/halls` | Assign exam rooms + invigilators for offline exams | C-EC-04 |
| 94 | Active Exams Monitor | `/exam-controller/monitor` | Live view of ongoing online exams: attempt count, malpractice flags | C-EC-05 |
| 95 | Malpractice Logs | `/exam-controller/malpractice` | Review flagged malpractice events — take action | C-EC-06 |
| 96 | Results Compilation | `/exam-controller/results` | Compile results from multiple exams into one publication | C-EC-07 |
| 97 | Publish Results | `/exam-controller/results/:id/publish` | Review compiled results then release to students | C-EC-08 |
| 98 | Grade Cards | `/exam-controller/grade-cards` | View/download generated grade cards per class | C-EC-09 |
| 99 | Exam Reports | `/exam-controller/reports` | Pass %, topper list, subject-wise performance charts | C-EC-10 |

---

## 8. Academic Coordinator Pages

> Backend: **Dev-B** | Frontend: **Dev-C**

| # | Page Name | Route | Description | Task ID |
|---|---|---|---|---|
| 100 | Coordinator Dashboard | `/coordinator/dashboard` | Timetable conflicts, substitutions today, upcoming events | C-AC-01 |
| 101 | Timetable Builder | `/coordinator/timetable` | Create/edit weekly timetable slots for all classes | C-AC-02 |
| 102 | Timetable Grid View | `/coordinator/timetable/grid` | Visual grid — all classes vs all periods, drag to assign | C-AC-03 |
| 103 | Teacher Conflict Checker | `/coordinator/timetable/conflicts` | Highlight same-slot double-bookings for teachers | C-AC-04 |
| 104 | Substitution Management | `/coordinator/substitutions` | List of today's / upcoming substitutions | C-AC-05 |
| 105 | Add Substitution | `/coordinator/substitutions/new` | Assign substitute teacher for a specific slot + date | C-AC-06 |
| 106 | Academic Calendar | `/coordinator/calendar` | Holidays, events, exam weeks, term dates | C-AC-07 |
| 107 | Post Academic Notice | `/coordinator/notices/new` | Post academic schedule notices to classes | C-AC-08 |

---

## 9. Accountant Pages

> Backend: **Dev-B** (Finance module APIs B-113 to B-120)  
> Frontend: **Dev-C**

| # | Page Name | Route | Description | Task ID |
|---|---|---|---|---|
| 108 | Accountant Dashboard | `/accountant/dashboard` | Today's collection, total dues, overdue count, monthly chart | C-AC-F01 |
| 109 | Fee Structure Setup | `/accountant/fee-structure` | Define fee heads + amounts per academic year | C-AC-F02 |
| 110 | Student Fee Accounts | `/accountant/accounts` | All students: fee paid, balance due, status filter | C-AC-F03 |
| 111 | Student Fee Detail | `/accountant/accounts/:studentId` | Individual fee account: installments, payments, scholarships | C-AC-F04 |
| 112 | Record Payment | `/accountant/payments/new` | Collect fee — select student, amount, mode, generate receipt | C-AC-F05 |
| 113 | Receipt View / Print | `/accountant/payments/:id/receipt` | Printable receipt (A4 / thermal) | C-AC-F06 |
| 114 | Fee Defaulters | `/accountant/defaulters` | Students with overdue/unpaid — filter by class, export | C-AC-F07 |
| 115 | Scholarship Management | `/accountant/scholarships` | Create scholarship schemes, grant to students | C-AC-F08 |
| 116 | Installment Schedule | `/accountant/installments` | All upcoming installment due dates with status | C-AC-F09 |
| 117 | Finance Reports | `/accountant/reports` | Daily/monthly collection report, export to Excel | C-AC-F10 |

---

## 10. Student Pages

> Backend: **Dev-B** | Frontend: **Dev-C**  
> All data scoped to own enrollment only

| # | Page Name | Route | Description | Task ID |
|---|---|---|---|---|
| 118 | Student Dashboard | `/student/dashboard` | Today's classes, attendance %, pending assignments, upcoming exams, recent notices | C-ST-01 |
| 119 | My Profile | `/student/profile` | Own profile: personal info, roll no, class, photo update | C-ST-02 |
| 120 | My Attendance | `/student/attendance` | Subject-wise attendance table + percentage bar chart | C-ST-03 |
| 121 | Attendance Calendar | `/student/attendance/calendar` | Month-view calendar: green = present, red = absent | C-ST-04 |
| 122 | Apply Leave | `/student/attendance/leaves/new` | Submit leave request with date range, reason, document | C-ST-05 |
| 123 | My Timetable | `/student/timetable` | Weekly grid of own class schedule | C-ST-06 |
| 124 | Exam List | `/student/examinations` | Upcoming / ongoing / completed exams for own class | C-ST-07 |
| 125 | Exam Attempt Screen | `/student/examinations/:id/attempt` | Full-screen timed exam: question nav, answer, submit | C-ST-08 |
| 126 | Exam Result View | `/student/examinations/:id/result` | Score, per-question breakdown, feedback (if allowed) | C-ST-09 |
| 127 | Assignment List | `/student/assignments` | All assignments: pending, submitted, approved, rejected | C-ST-10 |
| 128 | Assignment Detail | `/student/assignments/:id` | Instructions, due date, file upload, submission history | C-ST-11 |
| 129 | Milestone Progress | `/student/assignments/:id/milestones` | Stage-by-stage progress stepper, unlock status | C-ST-12 |
| 130 | Content Library | `/student/content` | Browse notes/videos/slides by subject → chapter → type | C-ST-13 |
| 131 | Content Player | `/student/content/:id` | In-browser PDF viewer or video player | C-ST-14 |
| 132 | Results | `/student/results` | Published results list — click to see subject breakdown | C-ST-15 |
| 133 | Result Detail | `/student/results/:id` | Subject scores table, grade, rank, remarks | C-ST-16 |
| 134 | Grade Card Download | `/student/results/:id/grade-card` | Download PDF grade card | C-ST-17 |
| 135 | Notice Board | `/student/notices` | All notices (institution + dept + class) feed, pinned first | C-ST-18 |
| 136 | Discussion Forum | `/student/discussion` | Threads in own class/subjects — post, reply, upvote | C-ST-19 |
| 137 | My Fee Account | `/student/fees` | Fee summary, installments paid/due, download receipts | C-ST-20 |

---

## 11. Parent Pages

> School-type institutions only  
> Backend: **Dev-B** | Frontend: **Dev-C**  
> All data scoped to own child only

| # | Page Name | Route | Description | Task ID |
|---|---|---|---|---|
| 138 | Parent Dashboard | `/parent/dashboard` | Child's attendance %, upcoming exams, recent notices, fee due alert | C-PA-01 |
| 139 | Child Attendance | `/parent/attendance` | Subject-wise attendance, same view as student but labelled child's name | C-PA-02 |
| 140 | Attendance Calendar | `/parent/attendance/calendar` | Month calendar for child | C-PA-03 |
| 141 | Child Timetable | `/parent/timetable` | Child's weekly class schedule | C-PA-04 |
| 142 | Child Results | `/parent/results` | Published results for child — subject breakdown | C-PA-05 |
| 143 | Grade Card | `/parent/results/:id/grade-card` | Download child's grade card PDF | C-PA-06 |
| 144 | Notice Board | `/parent/notices` | Notices relevant to child's class + institution | C-PA-07 |
| 145 | Fee Account | `/parent/fees` | Child's fee: paid, balance due, installments, download receipts | C-PA-08 |

---

## 12. Librarian Pages

> Requires Library module enabled  
> Backend: **Dev-B** (B-70 to B-75) | Frontend: **Dev-C**

| # | Page Name | Route | Description | Task ID |
|---|---|---|---|---|
| 146 | Library Dashboard | `/library/dashboard` | Total books, issued today, overdue count, new arrivals | C-LB-01 |
| 147 | Book Catalogue | `/library/books` | Search, filter, add, edit books. Available copies count. | C-LB-02 |
| 148 | Book Detail | `/library/books/:id` | Title info, copies list, issue history | C-LB-03 |
| 149 | Issue Book | `/library/issues/new` | Select student/staff + book copy → record issue + due date | C-LB-04 |
| 150 | Return Book | `/library/issues/:id/return` | Record return, calculate and collect fine if overdue | C-LB-05 |
| 151 | Issued Books List | `/library/issues` | All active issues — filter by borrower, overdue flag | C-LB-06 |
| 152 | Overdue List | `/library/overdue` | Overdue books: borrower, days late, fine amount | C-LB-07 |
| 153 | E-Resources | `/library/e-resources` | Upload / manage digital resources: eBooks, journals, links | C-LB-08 |

---

## 13. Hostel Warden Pages

> Requires Hostel module enabled  
> Backend: **Dev-B** (B-76 to B-80) | Frontend: **Dev-C**

| # | Page Name | Route | Description | Task ID |
|---|---|---|---|---|
| 154 | Hostel Dashboard | `/hostel/dashboard` | Occupancy %, today's absentees, pending leaves, open complaints | C-HW-01 |
| 155 | Blocks & Rooms | `/hostel/rooms` | Block list → room list → occupants per room | C-HW-02 |
| 156 | Room Allotment | `/hostel/allotments/new` | Assign student to room + bed for current academic year | C-HW-03 |
| 157 | Allotment List | `/hostel/allotments` | All current allotments, vacate / transfer option | C-HW-04 |
| 158 | Hostel Attendance | `/hostel/attendance` | Mark daily night attendance: select block → mark per room | C-HW-05 |
| 159 | Leave Requests | `/hostel/leaves` | Pending leave requests — approve / reject with note | C-HW-06 |
| 160 | Complaints Board | `/hostel/complaints` | All complaints: category filter, assign, resolve | C-HW-07 |
| 161 | Hostel Notices | `/hostel/notices/new` | Post notice to hostel residents | C-HW-08 |

---

## 14. Transport Manager Pages

> Requires Transport module enabled  
> Backend: **Dev-B** (B-81 to B-84) | Frontend: **Dev-C**

| # | Page Name | Route | Description | Task ID |
|---|---|---|---|---|
| 162 | Transport Dashboard | `/transport/dashboard` | Active routes count, students assigned, vehicle status | C-TR-01 |
| 163 | Route Management | `/transport/routes` | List routes: name, stops, vehicle, driver, student count | C-TR-02 |
| 164 | Route Detail / Edit | `/transport/routes/:id` | Edit route, add/reorder stops, assign vehicle + driver | C-TR-03 |
| 165 | Vehicle & Driver Management | `/transport/fleet` | Vehicles: reg no, capacity, expiry dates. Drivers: license, phone | C-TR-04 |
| 166 | Student Assignment | `/transport/assignments` | Assign students to routes + stops. Bulk import. | C-TR-05 |
| 167 | Transport Reports | `/transport/reports` | Route utilization, fee collection per route | C-TR-06 |

---

## 15. Placement Officer Pages

> Requires Placement module enabled  
> Backend: **Dev-B** (B-85 to B-92) | Frontend: **Dev-C**

| # | Page Name | Route | Description | Task ID |
|---|---|---|---|---|
| 168 | Placement Dashboard | `/placement/dashboard` | Drives active, applications today, offers issued, placed students % | C-PL-01 |
| 169 | Company Management | `/placement/companies` | Company list — add, edit, contact info, logo | C-PL-02 |
| 170 | Placement Drives | `/placement/drives` | All drives: upcoming/open/completed. Filter by company. | C-PL-03 |
| 171 | Create Drive | `/placement/drives/new` | Form: company, role, package, eligibility criteria, deadline | C-PL-04 |
| 172 | Drive Detail | `/placement/drives/:id` | Applicant list, shortlist/reject, interview rounds, offers | C-PL-05 |
| 173 | Applicant Tracking | `/placement/drives/:id/applicants` | Kanban/table: Applied → Shortlisted → Interview → Offer | C-PL-06 |
| 174 | Interview Rounds | `/placement/drives/:id/interviews` | Add rounds, schedule, record results per applicant | C-PL-07 |
| 175 | Offers Management | `/placement/offers` | All offers issued: accepted/declined/pending | C-PL-08 |
| 176 | Student Placement Profile | `/placement/students/:id` | View student's applications, interviews, offer history | C-PL-09 |
| 177 | Placement Reports | `/placement/reports` | Placed %, avg package, top recruiters, dept-wise stats | C-PL-10 |

---

## 16. HR Manager Pages

> Requires HR module enabled  
> Backend: **Dev-B** (B-93 to B-99) | Frontend: **Dev-C**

| # | Page Name | Route | Description | Task ID |
|---|---|---|---|---|
| 178 | HR Dashboard | `/hr/dashboard` | Total staff, on leave today, payroll due, pending appraisals | C-HR-01 |
| 179 | Staff Directory | `/hr/staff` | All staff: filter by dept, role, employment type | C-HR-02 |
| 180 | Staff Profile | `/hr/staff/:id` | Full HR profile: personal, banking, PF, documents | C-HR-03 |
| 181 | Add / Edit Staff | `/hr/staff/new` | Create staff HR profile (separate from user account) | C-HR-04 |
| 182 | Leave Policies | `/hr/leave-policies` | Create/edit leave types: CL, SL, EL — days, carry-forward | C-HR-05 |
| 183 | Leave Requests | `/hr/leave-requests` | All pending requests — approve / reject with reason | C-HR-06 |
| 184 | Leave Balance | `/hr/leave-balance` | Per-staff leave balance by type, year | C-HR-07 |
| 185 | Salary Structures | `/hr/salary` | Define salary components per staff / employment type | C-HR-08 |
| 186 | Payroll Run | `/hr/payroll` | Monthly payroll: select month → verify → process → lock | C-HR-09 |
| 187 | Payslips | `/hr/payslips` | All payslips: filter by month/staff — download PDF | C-HR-10 |
| 188 | Appraisal Cycles | `/hr/appraisals` | Create cycles, assign reviewers, track completion | C-HR-11 |
| 189 | Staff Documents | `/hr/staff/:id/documents` | Upload/view offer letters, contracts, certificates | C-HR-12 |

---

## 17. Admission Officer Pages

> Requires Admission module enabled  
> Backend: **Dev-B** (B-100 to B-105) | Frontend: **Dev-C**

| # | Page Name | Route | Description | Task ID |
|---|---|---|---|---|
| 190 | Admission Dashboard | `/admission/dashboard` | Applications received, under review, shortlisted, admitted — funnel chart | C-AD-01 |
| 191 | Admission Cycles | `/admission/cycles` | Create and manage admission intake cycles | C-AD-02 |
| 192 | Application List | `/admission/applications` | All applications: filter by status, dept, category | C-AD-03 |
| 193 | Application Detail | `/admission/applications/:id` | View applicant info, documents, change status, add notes | C-AD-04 |
| 194 | Document Verification | `/admission/applications/:id/documents` | Review uploaded docs, mark verified/rejected | C-AD-05 |
| 195 | Merit List | `/admission/merit-lists` | Generate and publish merit lists by dept + category | C-AD-06 |
| 196 | Enroll Student | `/admission/applications/:id/enroll` | Convert admitted applicant to active student user | C-AD-07 |
| 197 | Admission Reports | `/admission/reports` | Funnel, conversion rate, dept-wise breakdown | C-AD-08 |

---

## 18. Store Manager Pages

> Requires Inventory module enabled  
> Backend: **Dev-B** (B-106 to B-112) | Frontend: **Dev-C**

| # | Page Name | Route | Description | Task ID |
|---|---|---|---|---|
| 198 | Inventory Dashboard | `/inventory/dashboard` | Total items, low-stock alerts count, today's transactions, PO pending | C-SM-01 |
| 199 | Item Catalogue | `/inventory/items` | All items: search, filter by category, stock level indicator | C-SM-02 |
| 200 | Add / Edit Item | `/inventory/items/new` | Create item: name, code, unit, reorder level, location | C-SM-03 |
| 201 | Stock In | `/inventory/stock-in` | Record incoming stock — select item, quantity, reference PO | C-SM-04 |
| 202 | Stock Out | `/inventory/stock-out` | Issue items to dept — select item, qty, department | C-SM-05 |
| 203 | Vendor Management | `/inventory/vendors` | Add/edit vendors: name, contact, GST, address | C-SM-06 |
| 204 | Purchase Orders | `/inventory/purchase-orders` | All POs: draft/sent/delivered. Create new PO. | C-SM-07 |
| 205 | Purchase Order Detail | `/inventory/purchase-orders/:id` | Line items, approve, mark delivered, auto stock-in | C-SM-08 |

---

## 19. Shared / Public Pages

> Backend: **Dev-A** | Frontend: **Dev-C**

| # | Page Name | Route | Description | Task ID |
|---|---|---|---|---|
| 206 | Login | `/login` | Email + password login. Tenant auto-detected from subdomain. | C-PB-01 |
| 207 | Forgot Password | `/forgot-password` | Enter email → receive reset link via email | C-PB-02 |
| 208 | Reset Password | `/reset-password?token=` | Set new password via token from email | C-PB-03 |
| 209 | Public Admission Form | `/apply` | Prospective student application form (no login required) | C-PB-04 |
| 210 | 404 Not Found | `/404` | Custom 404 page with navigation back to dashboard | C-PB-05 |
| 211 | 403 Forbidden | `/403` | Access denied — role doesn't have permission | C-PB-06 |

---

## 20. Full Master Page Table

> 211 total pages · Developer C owns all frontend · Backend split between Dev-A and Dev-B

| Page # | Role | Page Name | Route | Backend Owner | Frontend Task |
|---|---|---|---|---|---|
| 1 | Super Admin | Dashboard | `/dashboard` | Dev-A | C-SA-01 |
| 2 | Super Admin | Institution List | `/institutions` | Dev-A | C-SA-02 |
| 3 | Super Admin | Institution Detail | `/institutions/:id` | Dev-A | C-SA-03 |
| 4 | Super Admin | Create Institution | `/institutions/new` | Dev-A | C-SA-04 |
| 5 | Super Admin | Plans Management | `/plans` | Dev-A | C-SA-05 |
| 6 | Super Admin | Platform Users | `/platform-users` | Dev-A | C-SA-06 |
| 7 | Super Admin | Audit Logs | `/audit-logs` | Dev-A | C-SA-07 |
| 8 | Super Admin | Platform Settings | `/settings` | Dev-A | C-SA-08 |
| 9 | Support Staff | Support Dashboard | `/support/dashboard` | Dev-A | C-SP-01 |
| 10 | Support Staff | Ticket List | `/support/tickets` | Dev-A | C-SP-02 |
| 11 | Support Staff | Ticket Detail | `/support/tickets/:id` | Dev-A | C-SP-03 |
| 12 | Support Staff | Institution Read-Only | `/support/institutions/:id` | Dev-A | C-SP-04 |
| 13 | Sales Executive | Sales Dashboard | `/sales/dashboard` | Dev-A | C-SL-01 |
| 14 | Sales Executive | Trial Institutions | `/sales/trials` | Dev-A | C-SL-02 |
| 15 | Sales Executive | Convert Trial | `/sales/trials/:id/convert` | Dev-A | C-SL-03 |
| 16 | Sales Executive | Subscriptions | `/sales/subscriptions` | Dev-A | C-SL-04 |
| 17 | Finance Manager | Finance Dashboard | `/finance/dashboard` | Dev-A | C-FM-01 |
| 18 | Finance Manager | Invoices | `/finance/invoices` | Dev-A | C-FM-02 |
| 19 | Finance Manager | Payment Records | `/finance/payments` | Dev-A | C-FM-03 |
| 20 | Finance Manager | Revenue Reports | `/finance/reports` | Dev-A | C-FM-04 |
| 21 | Institution Admin | Admin Dashboard | `/dashboard` | Dev-A | C-IA-01 |
| 22 | Institution Admin | Department Management | `/departments` | Dev-A | C-IA-02 |
| 23 | Institution Admin | Department Detail | `/departments/:id` | Dev-A | C-IA-03 |
| 24 | Institution Admin | Academic Year Setup | `/academic-years` | Dev-A | C-IA-04 |
| 25 | Institution Admin | Class Management | `/classes` | Dev-A | C-IA-05 |
| 26 | Institution Admin | Class Detail | `/classes/:id` | Dev-A | C-IA-06 |
| 27 | Institution Admin | Subject Management | `/subjects` | Dev-A | C-IA-07 |
| 28 | Institution Admin | User Management | `/users` | Dev-A | C-IA-08 |
| 29 | Institution Admin | User Detail | `/users/:id` | Dev-A | C-IA-09 |
| 30 | Institution Admin | Role Assignment | `/users/:id/roles` | Dev-A | C-IA-10 |
| 31 | Institution Admin | Student Enrollment | `/enrollments` | Dev-A | C-IA-11 |
| 32 | Institution Admin | Parent–Student Links | `/parent-links` | Dev-A | C-IA-12 |
| 33 | Institution Admin | Settings — General | `/settings/general` | Dev-A | C-IA-13 |
| 34 | Institution Admin | Settings — Modules | `/settings/modules` | Dev-A | C-IA-14 |
| 35 | Institution Admin | Settings — Fee Structure | `/settings/fees` | Dev-B | C-IA-15 |
| 36 | Institution Admin | Settings — Notifications | `/settings/notifications` | Dev-A | C-IA-16 |
| 37 | Institution Admin | Support Tickets | `/support` | Dev-A | C-IA-17 |
| 38 | Institution Admin | Audit Logs | `/audit-logs` | Dev-A | C-IA-18 |
| 39 | Principal | Dashboard | `/principal/dashboard` | Dev-A+B | C-PR-01 |
| 40 | Principal | Attendance Overview | `/principal/attendance` | Dev-B | C-PR-02 |
| 41 | Principal | Exam Schedule View | `/principal/examinations` | Dev-B | C-PR-03 |
| 42 | Principal | Results Overview | `/principal/results` | Dev-B | C-PR-04 |
| 43 | Principal | Staff Directory | `/principal/staff` | Dev-A | C-PR-05 |
| 44 | Principal | Student Directory | `/principal/students` | Dev-A | C-PR-06 |
| 45 | Principal | Notice Board | `/principal/notices` | Dev-B | C-PR-07 |
| 46 | Principal | Post Notice | `/principal/notices/new` | Dev-B | C-PR-08 |
| 47 | Principal | Timetable View | `/principal/timetable` | Dev-B | C-PR-09 |
| 48 | Principal | Reports | `/principal/reports` | Dev-B | C-PR-10 |
| 49 | Vice Principal | Dashboard | `/vp/dashboard` | Dev-A+B | C-VP-01 |
| 50 | Vice Principal | Attendance Report | `/vp/attendance` | Dev-B | C-VP-02 |
| 51 | Vice Principal | Exam Schedule View | `/vp/examinations` | Dev-B | C-VP-03 |
| 52 | Vice Principal | Results View | `/vp/results` | Dev-B | C-VP-04 |
| 53 | Vice Principal | Notice Board | `/vp/notices` | Dev-B | C-VP-05 |
| 54 | Vice Principal | Post Notice | `/vp/notices/new` | Dev-B | C-VP-06 |
| 55 | Vice Principal | Staff Directory | `/vp/staff` | Dev-A | C-VP-07 |
| 56 | HOD | Dashboard | `/hod/dashboard` | Dev-B | C-HD-01 |
| 57 | HOD | Department Attendance | `/hod/attendance` | Dev-B | C-HD-02 |
| 58 | HOD | Attendance Report | `/hod/attendance/report` | Dev-B | C-HD-03 |
| 59 | HOD | Exam List (Dept) | `/hod/examinations` | Dev-B | C-HD-04 |
| 60 | HOD | Assignment Overview | `/hod/assignments` | Dev-B | C-HD-05 |
| 61 | HOD | Results Overview | `/hod/results` | Dev-B | C-HD-06 |
| 62 | HOD | Teacher List | `/hod/teachers` | Dev-A | C-HD-07 |
| 63 | HOD | Mentor Assignments | `/hod/mentors` | Dev-A | C-HD-08 |
| 64 | HOD | Notice Board | `/hod/notices` | Dev-B | C-HD-09 |
| 65 | HOD | Post Notice | `/hod/notices/new` | Dev-B | C-HD-10 |
| 66 | HOD | Discussion Moderation | `/hod/discussion` | Dev-B | C-HD-11 |
| 67 | HOD | Timetable View | `/hod/timetable` | Dev-B | C-HD-12 |
| 68 | Teacher | Dashboard | `/teacher/dashboard` | Dev-B | C-TC-01 |
| 69 | Teacher | My Schedule | `/teacher/schedule` | Dev-B | C-TC-02 |
| 70 | Teacher | Mark Attendance | `/teacher/attendance/mark` | Dev-B | C-TC-03 |
| 71 | Teacher | Attendance Sessions | `/teacher/attendance/sessions` | Dev-B | C-TC-04 |
| 72 | Teacher | Session Detail | `/teacher/attendance/sessions/:id` | Dev-B | C-TC-05 |
| 73 | Teacher | Leave Requests | `/teacher/attendance/leaves` | Dev-B | C-TC-06 |
| 74 | Teacher | Exam List | `/teacher/examinations` | Dev-B | C-TC-07 |
| 75 | Teacher | Create Exam | `/teacher/examinations/new` | Dev-B | C-TC-08 |
| 76 | Teacher | Exam Detail / Edit | `/teacher/examinations/:id` | Dev-B | C-TC-09 |
| 77 | Teacher | Add Questions | `/teacher/examinations/:id/questions` | Dev-B | C-TC-10 |
| 78 | Teacher | Exam Results | `/teacher/examinations/:id/results` | Dev-B | C-TC-11 |
| 79 | Teacher | Assignment List | `/teacher/assignments` | Dev-B | C-TC-12 |
| 80 | Teacher | Create Assignment | `/teacher/assignments/new` | Dev-B | C-TC-13 |
| 81 | Teacher | Assignment Detail | `/teacher/assignments/:id` | Dev-B | C-TC-14 |
| 82 | Teacher | Submission Review | `/teacher/assignments/:id/submissions` | Dev-B | C-TC-15 |
| 83 | Teacher | Submission Detail | `/teacher/submissions/:id` | Dev-B | C-TC-16 |
| 84 | Teacher | Content Upload List | `/teacher/content` | Dev-B | C-TC-17 |
| 85 | Teacher | Upload Content | `/teacher/content/upload` | Dev-B | C-TC-18 |
| 86 | Teacher | Notice Board | `/teacher/notices` | Dev-B | C-TC-19 |
| 87 | Teacher | Post Notice | `/teacher/notices/new` | Dev-B | C-TC-20 |
| 88 | Teacher | Discussion Forum | `/teacher/discussion` | Dev-B | C-TC-21 |
| 89 | Teacher | Thread Detail | `/teacher/discussion/:id` | Dev-B | C-TC-22 |
| 90 | Exam Controller | Dashboard | `/exam-controller/dashboard` | Dev-B | C-EC-01 |
| 91 | Exam Controller | Exam Schedule | `/exam-controller/schedule` | Dev-B | C-EC-02 |
| 92 | Exam Controller | Create Schedule | `/exam-controller/schedule/new` | Dev-B | C-EC-03 |
| 93 | Exam Controller | Hall Allocation | `/exam-controller/halls` | Dev-B | C-EC-04 |
| 94 | Exam Controller | Active Exams Monitor | `/exam-controller/monitor` | Dev-B | C-EC-05 |
| 95 | Exam Controller | Malpractice Logs | `/exam-controller/malpractice` | Dev-B | C-EC-06 |
| 96 | Exam Controller | Results Compilation | `/exam-controller/results` | Dev-B | C-EC-07 |
| 97 | Exam Controller | Publish Results | `/exam-controller/results/:id/publish` | Dev-B | C-EC-08 |
| 98 | Exam Controller | Grade Cards | `/exam-controller/grade-cards` | Dev-B | C-EC-09 |
| 99 | Exam Controller | Exam Reports | `/exam-controller/reports` | Dev-B | C-EC-10 |
| 100 | Acad. Coordinator | Dashboard | `/coordinator/dashboard` | Dev-B | C-AC-01 |
| 101 | Acad. Coordinator | Timetable Builder | `/coordinator/timetable` | Dev-B | C-AC-02 |
| 102 | Acad. Coordinator | Timetable Grid | `/coordinator/timetable/grid` | Dev-B | C-AC-03 |
| 103 | Acad. Coordinator | Conflict Checker | `/coordinator/timetable/conflicts` | Dev-B | C-AC-04 |
| 104 | Acad. Coordinator | Substitutions | `/coordinator/substitutions` | Dev-B | C-AC-05 |
| 105 | Acad. Coordinator | Add Substitution | `/coordinator/substitutions/new` | Dev-B | C-AC-06 |
| 106 | Acad. Coordinator | Academic Calendar | `/coordinator/calendar` | Dev-B | C-AC-07 |
| 107 | Acad. Coordinator | Post Notice | `/coordinator/notices/new` | Dev-B | C-AC-08 |
| 108 | Accountant | Dashboard | `/accountant/dashboard` | Dev-B | C-AC-F01 |
| 109 | Accountant | Fee Structure Setup | `/accountant/fee-structure` | Dev-B | C-AC-F02 |
| 110 | Accountant | Student Fee Accounts | `/accountant/accounts` | Dev-B | C-AC-F03 |
| 111 | Accountant | Student Fee Detail | `/accountant/accounts/:studentId` | Dev-B | C-AC-F04 |
| 112 | Accountant | Record Payment | `/accountant/payments/new` | Dev-B | C-AC-F05 |
| 113 | Accountant | Receipt View/Print | `/accountant/payments/:id/receipt` | Dev-B | C-AC-F06 |
| 114 | Accountant | Fee Defaulters | `/accountant/defaulters` | Dev-B | C-AC-F07 |
| 115 | Accountant | Scholarship Management | `/accountant/scholarships` | Dev-B | C-AC-F08 |
| 116 | Accountant | Installment Schedule | `/accountant/installments` | Dev-B | C-AC-F09 |
| 117 | Accountant | Finance Reports | `/accountant/reports` | Dev-B | C-AC-F10 |
| 118 | Student | Dashboard | `/student/dashboard` | Dev-B | C-ST-01 |
| 119 | Student | My Profile | `/student/profile` | Dev-A | C-ST-02 |
| 120 | Student | My Attendance | `/student/attendance` | Dev-B | C-ST-03 |
| 121 | Student | Attendance Calendar | `/student/attendance/calendar` | Dev-B | C-ST-04 |
| 122 | Student | Apply Leave | `/student/attendance/leaves/new` | Dev-B | C-ST-05 |
| 123 | Student | My Timetable | `/student/timetable` | Dev-B | C-ST-06 |
| 124 | Student | Exam List | `/student/examinations` | Dev-B | C-ST-07 |
| 125 | Student | Exam Attempt Screen | `/student/examinations/:id/attempt` | Dev-B | C-ST-08 |
| 126 | Student | Exam Result View | `/student/examinations/:id/result` | Dev-B | C-ST-09 |
| 127 | Student | Assignment List | `/student/assignments` | Dev-B | C-ST-10 |
| 128 | Student | Assignment Detail | `/student/assignments/:id` | Dev-B | C-ST-11 |
| 129 | Student | Milestone Progress | `/student/assignments/:id/milestones` | Dev-B | C-ST-12 |
| 130 | Student | Content Library | `/student/content` | Dev-B | C-ST-13 |
| 131 | Student | Content Player | `/student/content/:id` | Dev-B | C-ST-14 |
| 132 | Student | Results | `/student/results` | Dev-B | C-ST-15 |
| 133 | Student | Result Detail | `/student/results/:id` | Dev-B | C-ST-16 |
| 134 | Student | Grade Card Download | `/student/results/:id/grade-card` | Dev-B | C-ST-17 |
| 135 | Student | Notice Board | `/student/notices` | Dev-B | C-ST-18 |
| 136 | Student | Discussion Forum | `/student/discussion` | Dev-B | C-ST-19 |
| 137 | Student | My Fee Account | `/student/fees` | Dev-B | C-ST-20 |
| 138 | Parent | Dashboard | `/parent/dashboard` | Dev-B | C-PA-01 |
| 139 | Parent | Child Attendance | `/parent/attendance` | Dev-B | C-PA-02 |
| 140 | Parent | Attendance Calendar | `/parent/attendance/calendar` | Dev-B | C-PA-03 |
| 141 | Parent | Child Timetable | `/parent/timetable` | Dev-B | C-PA-04 |
| 142 | Parent | Child Results | `/parent/results` | Dev-B | C-PA-05 |
| 143 | Parent | Grade Card | `/parent/results/:id/grade-card` | Dev-B | C-PA-06 |
| 144 | Parent | Notice Board | `/parent/notices` | Dev-B | C-PA-07 |
| 145 | Parent | Fee Account | `/parent/fees` | Dev-B | C-PA-08 |
| 146 | Librarian | Library Dashboard | `/library/dashboard` | Dev-B | C-LB-01 |
| 147 | Librarian | Book Catalogue | `/library/books` | Dev-B | C-LB-02 |
| 148 | Librarian | Book Detail | `/library/books/:id` | Dev-B | C-LB-03 |
| 149 | Librarian | Issue Book | `/library/issues/new` | Dev-B | C-LB-04 |
| 150 | Librarian | Return Book | `/library/issues/:id/return` | Dev-B | C-LB-05 |
| 151 | Librarian | Issued Books List | `/library/issues` | Dev-B | C-LB-06 |
| 152 | Librarian | Overdue List | `/library/overdue` | Dev-B | C-LB-07 |
| 153 | Librarian | E-Resources | `/library/e-resources` | Dev-B | C-LB-08 |
| 154 | Hostel Warden | Hostel Dashboard | `/hostel/dashboard` | Dev-B | C-HW-01 |
| 155 | Hostel Warden | Blocks & Rooms | `/hostel/rooms` | Dev-B | C-HW-02 |
| 156 | Hostel Warden | Room Allotment | `/hostel/allotments/new` | Dev-B | C-HW-03 |
| 157 | Hostel Warden | Allotment List | `/hostel/allotments` | Dev-B | C-HW-04 |
| 158 | Hostel Warden | Hostel Attendance | `/hostel/attendance` | Dev-B | C-HW-05 |
| 159 | Hostel Warden | Leave Requests | `/hostel/leaves` | Dev-B | C-HW-06 |
| 160 | Hostel Warden | Complaints Board | `/hostel/complaints` | Dev-B | C-HW-07 |
| 161 | Hostel Warden | Hostel Notices | `/hostel/notices/new` | Dev-B | C-HW-08 |
| 162 | Transport Manager | Transport Dashboard | `/transport/dashboard` | Dev-B | C-TR-01 |
| 163 | Transport Manager | Route Management | `/transport/routes` | Dev-B | C-TR-02 |
| 164 | Transport Manager | Route Detail / Edit | `/transport/routes/:id` | Dev-B | C-TR-03 |
| 165 | Transport Manager | Vehicle & Driver Mgmt | `/transport/fleet` | Dev-B | C-TR-04 |
| 166 | Transport Manager | Student Assignment | `/transport/assignments` | Dev-B | C-TR-05 |
| 167 | Transport Manager | Transport Reports | `/transport/reports` | Dev-B | C-TR-06 |
| 168 | Placement Officer | Placement Dashboard | `/placement/dashboard` | Dev-B | C-PL-01 |
| 169 | Placement Officer | Company Management | `/placement/companies` | Dev-B | C-PL-02 |
| 170 | Placement Officer | Placement Drives | `/placement/drives` | Dev-B | C-PL-03 |
| 171 | Placement Officer | Create Drive | `/placement/drives/new` | Dev-B | C-PL-04 |
| 172 | Placement Officer | Drive Detail | `/placement/drives/:id` | Dev-B | C-PL-05 |
| 173 | Placement Officer | Applicant Tracking | `/placement/drives/:id/applicants` | Dev-B | C-PL-06 |
| 174 | Placement Officer | Interview Rounds | `/placement/drives/:id/interviews` | Dev-B | C-PL-07 |
| 175 | Placement Officer | Offers Management | `/placement/offers` | Dev-B | C-PL-08 |
| 176 | Placement Officer | Student Placement Profile | `/placement/students/:id` | Dev-B | C-PL-09 |
| 177 | Placement Officer | Placement Reports | `/placement/reports` | Dev-B | C-PL-10 |
| 178 | HR Manager | HR Dashboard | `/hr/dashboard` | Dev-B | C-HR-01 |
| 179 | HR Manager | Staff Directory | `/hr/staff` | Dev-B | C-HR-02 |
| 180 | HR Manager | Staff Profile | `/hr/staff/:id` | Dev-B | C-HR-03 |
| 181 | HR Manager | Add / Edit Staff | `/hr/staff/new` | Dev-B | C-HR-04 |
| 182 | HR Manager | Leave Policies | `/hr/leave-policies` | Dev-B | C-HR-05 |
| 183 | HR Manager | Leave Requests | `/hr/leave-requests` | Dev-B | C-HR-06 |
| 184 | HR Manager | Leave Balance | `/hr/leave-balance` | Dev-B | C-HR-07 |
| 185 | HR Manager | Salary Structures | `/hr/salary` | Dev-B | C-HR-08 |
| 186 | HR Manager | Payroll Run | `/hr/payroll` | Dev-B | C-HR-09 |
| 187 | HR Manager | Payslips | `/hr/payslips` | Dev-B | C-HR-10 |
| 188 | HR Manager | Appraisal Cycles | `/hr/appraisals` | Dev-B | C-HR-11 |
| 189 | HR Manager | Staff Documents | `/hr/staff/:id/documents` | Dev-B | C-HR-12 |
| 190 | Admission Officer | Admission Dashboard | `/admission/dashboard` | Dev-B | C-AD-01 |
| 191 | Admission Officer | Admission Cycles | `/admission/cycles` | Dev-B | C-AD-02 |
| 192 | Admission Officer | Application List | `/admission/applications` | Dev-B | C-AD-03 |
| 193 | Admission Officer | Application Detail | `/admission/applications/:id` | Dev-B | C-AD-04 |
| 194 | Admission Officer | Document Verification | `/admission/applications/:id/documents` | Dev-B | C-AD-05 |
| 195 | Admission Officer | Merit List | `/admission/merit-lists` | Dev-B | C-AD-06 |
| 196 | Admission Officer | Enroll Student | `/admission/applications/:id/enroll` | Dev-B | C-AD-07 |
| 197 | Admission Officer | Admission Reports | `/admission/reports` | Dev-B | C-AD-08 |
| 198 | Store Manager | Inventory Dashboard | `/inventory/dashboard` | Dev-B | C-SM-01 |
| 199 | Store Manager | Item Catalogue | `/inventory/items` | Dev-B | C-SM-02 |
| 200 | Store Manager | Add / Edit Item | `/inventory/items/new` | Dev-B | C-SM-03 |
| 201 | Store Manager | Stock In | `/inventory/stock-in` | Dev-B | C-SM-04 |
| 202 | Store Manager | Stock Out | `/inventory/stock-out` | Dev-B | C-SM-05 |
| 203 | Store Manager | Vendor Management | `/inventory/vendors` | Dev-B | C-SM-06 |
| 204 | Store Manager | Purchase Orders | `/inventory/purchase-orders` | Dev-B | C-SM-07 |
| 205 | Store Manager | Purchase Order Detail | `/inventory/purchase-orders/:id` | Dev-B | C-SM-08 |
| 206 | Public | Login | `/login` | Dev-A | C-PB-01 |
| 207 | Public | Forgot Password | `/forgot-password` | Dev-A | C-PB-02 |
| 208 | Public | Reset Password | `/reset-password` | Dev-A | C-PB-03 |
| 209 | Public | Public Admission Form | `/apply` | Dev-B | C-PB-04 |
| 210 | Public | 404 Not Found | `/404` | — | C-PB-05 |
| 211 | Public | 403 Forbidden | `/403` | — | C-PB-06 |

---

## Page Count by Developer

### Dev-C (Frontend) — All 211 Pages

| Category | Pages |
|---|---|
| Platform (Super Admin + Support + Sales + Finance) | 20 |
| Institution Admin | 18 |
| Principal + Vice Principal | 17 |
| HOD | 12 |
| Teacher | 22 |
| Exam Controller | 10 |
| Academic Coordinator | 8 |
| Accountant | 10 |
| Student | 20 |
| Parent | 8 |
| Librarian (optional) | 8 |
| Hostel Warden (optional) | 8 |
| Transport Manager (optional) | 6 |
| Placement Officer (optional) | 10 |
| HR Manager (optional) | 12 |
| Admission Officer (optional) | 8 |
| Store Manager (optional) | 8 |
| Public / Shared | 6 |
| **Total** | **211 pages** |

### Dev-A (Backend) — Pages where A owns the API

| Area | Page Count |
|---|---|
| Platform (Super Admin, Support, Sales, Finance) | 20 pages |
| Institution structure (Admin setup, user mgmt, RBAC) | 20 pages |
| Auth system (login, reset, sessions) | 3 pages |
| Analytics APIs (Principal, VP reports) | 6 pages |
| **Total backend ownership** | ~49 pages |

### Dev-B (Backend) — Pages where B owns the API

| Area | Page Count |
|---|---|
| Core LMS modules (attendance, exam, assignment, notice, discussion, content, results, timetable) | 82 pages |
| Student + Parent views | 28 pages |
| Optional modules (library, hostel, transport, placement, HR, admission, inventory, finance) | 52 pages |
| **Total backend ownership** | ~162 pages |

---

## Developer C — Recommended Build Order for All 211 Pages

```
SPRINT 1 (Week 1-2):   Pages 206-210 (auth + shell) → always first
SPRINT 2 (Week 3-4):   Pages 21-38 (institution admin setup) + 118-122 (student basics)
SPRINT 3 (Week 5-6):   Pages 68-89 (teacher full set) + 124-126 (student exam)
SPRINT 4 (Week 7-8):   Pages 90-99 (exam controller) + 127-134 (student assignment+results)
SPRINT 5 (Week 9-10):  Pages 56-67 (HOD) + 100-107 (coordinator) + 135-137 (student notice+fee)
SPRINT 6 (Week 9-10):  Pages 39-55 (principal+VP) + 138-145 (parent)
SPRINT 7 (Week 11-12): Pages 108-117 (accountant) + 146-167 (library, hostel, transport)
SPRINT 8 (Week 12-13): Pages 168-177 (placement) + 178-189 (HR)
SPRINT 9 (Week 13-14): Pages 190-205 (admission + inventory)
SPRINT 10 (Week 14):   Pages 1-20 (Super Admin, Support, Sales, Finance — platform layer)
SPRINT 11 (Week 15-16): Polish, mobile, PWA, Cypress tests
```

---

*Document version: 1.0*  
*Total pages: 211 · 22 roles · 15 modules · 3 developers*  
*Frontend: Dev-C owns all 211 pages*  
*Backend: Dev-A owns platform + foundation APIs · Dev-B owns all module APIs*

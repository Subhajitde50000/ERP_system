# ERP + LMS Platform — Role-Based Shared Pages

> These are pages that exist ONCE in the codebase but render differently based on the logged-in user's role.  
> Single URL → multiple views → one component with role-aware rendering.  
> Total Shared Role-Based Pages: 24 pages  
> Developer: **Dev-C (Frontend UI)** | Backend: **Dev-A + Dev-B**

---

## What Is a Role-Based Shared Page?

Instead of building `/principal/dashboard`, `/hod/dashboard`, `/teacher/dashboard`, `/student/dashboard` as 10 separate pages, we build **one** `/dashboard` page that switches its layout and data based on the logged-in user's role.

```
User logs in
     ↓
JWT decoded → role = "TEACHER"
     ↓
/dashboard renders → Teacher Dashboard layout
     ↓
Same URL, different content for each role
```

**Benefits:**
- One route to protect, one page to maintain
- Role logic centralized in one place
- Navigation always lands on `/dashboard` regardless of role

---

## How to Implement (Next.js Pattern)

```typescript
// app/(institution)/dashboard/page.tsx

import { getCurrentUser } from '@/lib/auth'
import { SuperAdminDashboard }       from '@/components/dashboards/SuperAdminDashboard'
import { PrincipalDashboard }        from '@/components/dashboards/PrincipalDashboard'
import { VicePrincipalDashboard }    from '@/components/dashboards/VicePrincipalDashboard'
import { HodDashboard }              from '@/components/dashboards/HodDashboard'
import { TeacherDashboard }          from '@/components/dashboards/TeacherDashboard'
import { ExamControllerDashboard }   from '@/components/dashboards/ExamControllerDashboard'
import { CoordinatorDashboard }      from '@/components/dashboards/CoordinatorDashboard'
import { AccountantDashboard }       from '@/components/dashboards/AccountantDashboard'
import { StudentDashboard }          from '@/components/dashboards/StudentDashboard'
import { ParentDashboard }           from '@/components/dashboards/ParentDashboard'
import { LibrarianDashboard }        from '@/components/dashboards/LibrarianDashboard'
import { HostelWardenDashboard }     from '@/components/dashboards/HostelWardenDashboard'
import { TransportManagerDashboard } from '@/components/dashboards/TransportManagerDashboard'
import { PlacementOfficerDashboard } from '@/components/dashboards/PlacementOfficerDashboard'
import { HrManagerDashboard }        from '@/components/dashboards/HrManagerDashboard'
import { AdmissionOfficerDashboard } from '@/components/dashboards/AdmissionOfficerDashboard'
import { StoreManagerDashboard }     from '@/components/dashboards/StoreManagerDashboard'

const DASHBOARD_MAP = {
  INSTITUTION_ADMIN:    InstitutionAdminDashboard,
  PRINCIPAL:            PrincipalDashboard,
  VICE_PRINCIPAL:       VicePrincipalDashboard,
  HOD:                  HodDashboard,
  TEACHER:              TeacherDashboard,
  MENTOR:               TeacherDashboard,          // same as Teacher
  EXAM_CONTROLLER:      ExamControllerDashboard,
  ACADEMIC_COORDINATOR: CoordinatorDashboard,
  ACCOUNTANT:           AccountantDashboard,
  STUDENT:              StudentDashboard,
  PARENT:               ParentDashboard,
  LIBRARIAN:            LibrarianDashboard,
  HOSTEL_WARDEN:        HostelWardenDashboard,
  TRANSPORT_MANAGER:    TransportManagerDashboard,
  PLACEMENT_OFFICER:    PlacementOfficerDashboard,
  HR_MANAGER:           HrManagerDashboard,
  ADMISSION_OFFICER:    AdmissionOfficerDashboard,
  STORE_MANAGER:        StoreManagerDashboard,
}

export default async function DashboardPage() {
  const user = await getCurrentUser()
  const primaryRole = user.roles[0]               // highest priority role
  const DashboardComponent = DASHBOARD_MAP[primaryRole]

  if (!DashboardComponent) return <Redirect to="/403" />
  return <DashboardComponent user={user} />
}
```

---

## Complete List of All Role-Based Shared Pages

---

### PAGE 1 — Dashboard `/dashboard`✅

**One URL. 17 different role views.**

| Role | What They See | API Calls |
|---|---|---|
| **Institution Admin** | Total students, total staff, active modules count, recent audit actions, support ticket status, fee collection today | `GET /dashboard/admin-stats` |
| **Principal** | Institution attendance %, exams this week, pass % this term, total notices, staff on leave today | `GET /dashboard/principal-stats` |
| **Vice Principal** | Same as Principal but dept-scoped. Delegated actions pending. | `GET /dashboard/vp-stats` |
| **HOD** | Dept attendance %, pending assignment reviews, exams in dept this week, teacher count, recent dept notice | `GET /dashboard/hod-stats` |
| **Teacher** | Today's periods (from timetable), pending submissions to review, upcoming exams created, recent notices for class | `GET /dashboard/teacher-stats` |
| **Mentor** | Assigned mentees (direct / team / class), their attendance %, at-risk alerts, upcoming exams, recent log | `GET /mentor/dashboard` |
| **Exam Controller** | Exams scheduled today, live exam count, pending result compilations, malpractice flags today | `GET /dashboard/exam-controller-stats` |
| **Academic Coordinator** | Substitutions today, timetable conflicts count, upcoming events, recent schedule changes | `GET /dashboard/coordinator-stats` |
| **Accountant** | Today's collection amount, total balance due, overdue count, upcoming installment dues, recent payments | `GET /dashboard/accountant-stats` |
| **Student** | Attendance % (overall + per subject), next exam, pending assignment, recent notices, next class from timetable | `GET /dashboard/student-stats` |
| **Parent** | Child's attendance %, child's next exam, fee due amount, recent notice for child's class | `GET /dashboard/parent-stats` |
| **Librarian** | Books issued today, overdue returns count, low stock alert, recent issues | `GET /dashboard/librarian-stats` |
| **Hostel Warden** | Today's absentees in hostel, pending leave requests, open complaints, room occupancy % | `GET /dashboard/warden-stats` |
| **Transport Manager** | Active routes count, students assigned, vehicles on road today, pending route issues | `GET /dashboard/transport-stats` |
| **Placement Officer** | Active drives count, applications today, interviews scheduled, offers pending acceptance | `GET /dashboard/placement-stats` |
| **HR Manager** | Staff on leave today, pending leave requests, payroll due this month, open appraisals | `GET /dashboard/hr-stats` |
| **Admission Officer** | Applications received today, under review, shortlisted, merit list pending | `GET /dashboard/admission-stats` |
| **Store Manager** | Low stock items count, pending POs, stock transactions today, total item categories | `GET /dashboard/store-stats` |

**Component Structure:**
```
/components/dashboards/
├── InstitutionAdminDashboard.tsx
├── PrincipalDashboard.tsx
├── VicePrincipalDashboard.tsx
├── HodDashboard.tsx
├── TeacherDashboard.tsx
├── ExamControllerDashboard.tsx
├── CoordinatorDashboard.tsx
├── AccountantDashboard.tsx
├── StudentDashboard.tsx
├── ParentDashboard.tsx
├── LibrarianDashboard.tsx
├── HostelWardenDashboard.tsx
├── TransportManagerDashboard.tsx
├── PlacementOfficerDashboard.tsx
├── HrManagerDashboard.tsx
├── AdmissionOfficerDashboard.tsx
└── StoreManagerDashboard.tsx
```

**Backend:** Dev-B builds `GET /dashboard/:roleKey-stats` endpoint  
**Frontend:** Dev-C builds 17 dashboard components, one per role  
**Task ID:** C-RB-01 (17 sub-components)

---

### PAGE 2 — Notice Board `/notices`                ✅

**One URL. Different post permissions and scopes per role.**

| Role | What They See | Can Post? | Post Scope |
|---|---|---|---|
| **Institution Admin** | All notices (institution + all depts + all classes) | ✅ Yes | Institution / Any dept / Any class |
| **Principal** | All notices | ✅ Yes | Institution / Any dept / Any class |
| **Vice Principal** | All notices | ✅ Yes | Dept / Class (not institution-wide) |
| **HOD** | Institution + own dept + own dept classes | ✅ Yes | Own dept / own dept classes only |
| **Teacher** | Institution + own dept + own classes | ✅ Yes | Own class only |
| **Exam Controller** | Institution + all notices | ✅ Yes | Institution / exam-related |
| **Academic Coordinator** | Institution + dept notices | ✅ Yes | Academic notices to classes |
| **Accountant** | Institution notices only | ❌ No | View only |
| **Student** | Institution + own dept + own class notices | ❌ No | View only |
| **Parent** | Institution + child's class notices | ❌ No | View only |
| **Librarian** | Institution notices only | ❌ No | View only |
| **Hostel Warden** | Institution + hostel-scope notices | ✅ Yes | Hostel residents only |
| **Transport Manager** | Institution notices | ❌ No | View only |
| **Placement Officer** | Institution + placement notices | ✅ Yes | Placement-eligible students |
| **HR Manager** | Institution + staff notices | ✅ Yes | All staff |
| **Admission Officer** | Institution notices | ❌ No | View only |
| **Store Manager** | Institution notices | ❌ No | View only |

**Component Logic:**
```typescript
// NoticeBoard renders one of these views:
// 1. Notice Feed (all roles) — paginated list, pinned first
// 2. Compose Button — shown only to roles with canPost = true
// 3. Scope Selector — shown when composing, options limited by role
// 4. Read Receipts tab — shown only to Admin / Principal

const canPost = usePermission('notice', 'CREATE')
const postScopes = usePostScopes() // returns allowed scopes for current role
```

**Backend:** `GET /notices/my` (auto-scoped by tenant middleware + role)  
**Task ID:** C-RB-02

---

### PAGE 3 — Discussion Forum `/discussion`        ✅

**One URL. Role determines what threads are visible and what actions are available.**

| Role | Scope Visible | Can Post Thread | Can Moderate |
|---|---|---|---|
| **HOD** | All dept threads (all classes + subjects) | ✅ Yes | ✅ Pin/lock/delete any thread in dept |
| **Teacher** | Own subject/class threads only | ✅ Yes | ✅ Pin/lock/delete in own subject |
| **Student** | Own class + own subject threads | ✅ Yes | ❌ No moderation |
| **Principal / VP** | All threads (read + moderate) | ✅ Yes | ✅ Full moderation |
| **Exam Controller** | Exam-related threads | ✅ Yes | ✅ Exam threads |
| **Academic Coordinator** | Academic threads | ✅ Yes | ❌ Limited |
| **Mentor** | Mentee group threads | ✅ Yes | ✅ Own group |

**Shared Components:**
- `<ThreadList>` — renders differently based on scope filter
- `<ThreadCard>` — shows pin/lock/delete buttons only to moderators
- `<NewThreadButton>` — shown to all roles who can post
- `<AcceptAnswerButton>` — shown only on Teacher's view of a thread in their subject

**Backend:** `GET /discussion/threads?scope=CLASS&scopeId=:id` (scoped by middleware)  
**Task ID:** C-RB-03

---

### PAGE 4 — Profile Page `/profile`✅

**One URL. Different fields visible and editable per role.**

| Role | Fields Visible | Can Edit |
|---|---|---|
| **All Staff (Teacher, HOD, etc.)** | Name, email, phone, avatar, employee code, department, designation | Name, phone, avatar only |
| **Student** | Name, email, phone, avatar, roll number, class, enrollment status | Name, phone, avatar only |
| **Parent** | Name, email, phone, avatar, linked children list | Name, phone, avatar only |
| **Institution Admin** | All fields + role assignments | Full edit |
| **HR Manager** | Views staff extended HR profile from here | Full HR edit |

**Backend:** `GET /users/me` (returns fields based on role)  
**Task ID:** C-RB-04

---

### PAGE 5 — Attendance View `/attendance`✅

**One URL. Completely different layout per role.**

| Role | View | Actions |
|---|---|---|
| **Teacher** | Class selector → student list → mark P/A/L per student | Mark, edit (before lock), lock session |
| **HOD** | Department-level heatmap: classes × dates | View only, export report |
| **Principal / VP** | Institution-level summary: dept × attendance % | View only, export |
| **Exam Controller** | Exam hall attendance for offline exams | Mark exam hall attendance |
| **Student** | Own attendance: subject-wise table + % bar chart | Apply for leave |
| **Parent** | Child's attendance (same as student view, child's data) | View only |
| **Academic Coordinator** | Class-wise attendance for scheduling | View only |

**Role-based rendering:**
```typescript
const AttendancePage = () => {
  const { primaryRole } = useAuth()

  if (primaryRole === 'TEACHER')              return <TeacherAttendanceView />
  if (primaryRole === 'HOD')                  return <HodAttendanceView />
  if (['PRINCIPAL','VICE_PRINCIPAL'].includes(primaryRole)) return <PrincipalAttendanceView />
  if (primaryRole === 'STUDENT')              return <StudentAttendanceView />
  if (primaryRole === 'PARENT')               return <ParentAttendanceView />
  if (primaryRole === 'EXAM_CONTROLLER')      return <ExamHallAttendanceView />
  return <GenericAttendanceView />
}
```

**Task ID:** C-RB-05

---

### PAGE 6 — Examination Page `/examination`✅

**One URL. Role determines create vs. attempt vs. monitor.**

| Role | View | Actions |
|---|---|---|
| **Teacher** | List of own exams (draft/published/completed) with status badges | Create, edit, publish, release results |
| **Exam Controller** | All exams across institution, schedule, hall allocation | Schedule, allocate halls, compile results |
| **HOD** | All exams in own dept | View only |
| **Principal / VP** | All exams institution-wide | View only |
| **Academic Coordinator** | Exam timetable (dates + classes) | View schedule |
| **Student** | Upcoming + past exams for own class | Attempt exam, view results |
| **Parent** | Child's upcoming + past exams | View only |

**Key sub-pages that are also role-based:**
- `/examination/:id` — Teacher sees question editor; Student sees exam attempt screen; Exam Controller sees submissions
- `/examination/:id/results` — Teacher grades; Student views own score; Exam Controller publishes

**Task ID:** C-RB-06

---

### PAGE 7 — Assignment Page `/assignments`✅

**One URL. Role determines create vs. submit vs. review.**

| Role | View | Actions |
|---|---|---|
| **Teacher** | All assignments created by them — status, submission count | Create, edit, close, review submissions |
| **HOD** | All dept assignments — pending review count per teacher | View only |
| **Student** | Own pending/submitted/approved assignments | Submit, view feedback, resubmit |
| **Parent** | Child's assignment status | View only |
| **Principal / VP** | Institution-wide assignment summary | View only |

**Task ID:** C-RB-07

---

### PAGE 8 — Content / Study Material `/content`✅

**One URL. Upload vs. browse view.**

| Role | View | Actions |
|---|---|---|
| **Teacher** | Own uploaded content list — organized by subject/chapter | Upload, edit metadata, hide/unhide, delete |
| **HOD** | All dept content across teachers | View only, can flag inappropriate content |
| **Student** | Browse content for own subjects: chapter → type | View, stream video, read PDF, download |
| **Parent** | Child's subject content (read-only browse) | View only |
| **Principal** | All content across institution | View only |

**Task ID:** C-RB-08

---

### PAGE 9 — Results `/results`✅

**One URL. Role determines what results are shown and what actions are available.**

| Role | View | Actions |
|---|---|---|
| **Teacher** | Results of own subject across classes | View, release subject results |
| **Exam Controller** | All results — compile + publish | Compile, approve, publish |
| **HOD** | Dept-wise result summary — pass %, toppers | View, export |
| **Principal / VP** | Institution-wide result summary | View, approve publication |
| **Student** | Own results: subject breakdown, grade, rank | Download grade card |
| **Parent** | Child's results | Download child's grade card |

**Task ID:** C-RB-09

---

### PAGE 10 — Timetable `/timetable`✅

**One URL. Create vs. view, class vs. personal schedule.**

| Role | View | Actions |
|---|---|---|
| **Academic Coordinator** | Full timetable builder grid — all classes | Create slots, bulk upload, detect conflicts, add substitutions |
| **Teacher** | Own weekly teaching schedule | View only |
| **HOD** | Dept timetable — all classes | View only |
| **Principal / VP** | All timetables | View only |
| **Student** | Own class weekly timetable | View only |
| **Parent** | Child's class timetable | View only |

**Task ID:** C-RB-10

---

### PAGE 11 — Fee Account `/fees`✅

**One URL. Different data scope and actions per role.**

| Role | View | Actions |
|---|---|---|
| **Accountant** | All student fee accounts — search, filter, collect | Record payment, generate receipt, apply scholarship, view defaulters |
| **Institution Admin** | Fee structure setup + overall collection summary | Set up fee heads, installment schedule |
| **Student** | Own fee account: paid, due, installments, receipts | Download receipt |
| **Parent** | Child's fee account | Download receipt |
| **Principal** | High-level fee collection summary | View only |

**Task ID:** C-RB-11

---

### PAGE 12 — User Directory `/users`✅

**One URL. Scope and edit permissions differ per role.**

| Role | Who They See | Actions |
|---|---|---|
| **Institution Admin** | ALL users in the institution | Create, edit, deactivate, assign roles, reset password |
| **HOD** | Teachers in own dept only | View profiles |
| **Principal / VP** | All staff + students | View profiles |
| **HR Manager** | All staff (for HR profile management) | View + edit HR profile |
| **Placement Officer** | Students (for placement eligibility check) | View profiles, check eligibility |
| **Admission Officer** | Newly enrolled students | View post-enrollment profiles |

**Task ID:** C-RB-12

---

### PAGE 13 — Leave Management `/leaves`

**One URL. Apply vs. approve view.**

| Role | View | Actions |
|---|---|---|
| **Student** | Own leave requests (attendance leaves) — history + status | Apply new leave, upload document |
| **Teacher** | Student leave requests for own classes — pending list | Approve / Reject |
| **HOD** | Dept leave requests (student) | Approve / Reject for dept |
| **Staff (Teacher, HOD, etc.)** | Own HR leave requests — balance, history | Apply HR leave |
| **HR Manager** | All staff leave requests | Approve / Reject, edit balances |
| **Hostel Warden** | Hostel leave requests from residents | Approve / Reject |

**Task ID:** C-RB-13

---

### PAGE 14 — Reports `/reports`✅

**One URL. Completely different report types per role.**

| Role | Reports Available |
|---|---|
| **Institution Admin** | Overall stats: enrolment, fee collection, attendance, results |
| **Principal / VP** | Academic performance: dept-wise attendance, result trends, exam pass % |
| **HOD** | Dept reports: teacher-wise attendance marking, subject-wise results |
| **Teacher** | Own class reports: attendance summary, assignment completion rate |
| **Exam Controller** | Exam reports: pass %, topper list, subject analysis, malpractice summary |
| **Accountant** | Finance reports: daily collection, fee defaulters, scholarship summary |
| **Placement Officer** | Placement stats: placed %, avg package, recruiter-wise, dept-wise |
| **HR Manager** | HR reports: headcount, leave utilization, payroll summary |
| **Transport Manager** | Route utilization, student count per route |
| **Librarian** | Book issue stats, overdue rates, most borrowed books |
| **Store Manager** | Stock movement report, low-stock history, vendor-wise PO report |

**Key pattern:** Role-based `<ReportSection>` components that only render if user has that role.

**Task ID:** C-RB-14

---

### PAGE 15 — Notifications `/notifications`✅

**One URL. Same layout, different notification types per role.**

| Role | Notification Types They Receive |
|---|---|
| **Teacher** | Submission received, assignment deadline approaching, exam starts soon, notice posted to class |
| **HOD** | Teacher marked attendance, exam published in dept, result released in dept, dept notice |
| **Student** | Attendance marked (own), exam result released, assignment approved/rejected, milestone unlocked, notice posted, fee due |
| **Parent** | Child absent, child's result released, fee due, class notice |
| **Exam Controller** | Exam attempt submitted (batch), malpractice flagged, result compilation ready |
| **Accountant** | Payment received, overdue fine triggered, fee installment due tomorrow |
| **HR Manager** | Leave request submitted, payroll run due |
| **Hostel Warden** | Student absent in hostel, leave request submitted, complaint raised |
| **Institution Admin** | New support ticket, module enabled/disabled, bulk enrollment done |
| **Placement Officer** | New application submitted, company confirmed drive, student offer accepted |
| **Admission Officer** | New application received, document verification pending |

**Shared component:** `<NotificationItem>` with `type` prop drives the icon, color, and deep-link URL.

**Task ID:** C-RB-15

---

### PAGE 16 — Settings `/settings`✅

**One URL. Sections shown/hidden per role.**

| Role | Settings Sections Visible |
|---|---|
| **Institution Admin** | General · Modules (toggle) · Fee Structure · Notifications · Academic Year · Branding |
| **Principal** | Academic Year (view) · Notification preferences |
| **Teacher** | Notification preferences · Change password |
| **Student** | Change password · Notification preferences |
| **HR Manager** | Leave policies · Salary structure defaults |
| **All roles** | Change password · Profile update |

**Task ID:** C-RB-16

---

### PAGE 17 — Search `/search`✅

**One URL. Results scoped by role.**

Global search bar available to all roles. What appears in results depends on role:

| Role | Can Search For |
|---|---|
| **Institution Admin** | Users, departments, classes, subjects, notices, audit logs |
| **Teacher** | Students in own class, own assignments, own content, notices |
| **Student** | Content (notes/videos), notices, discussion threads, exams |
| **HOD** | Teachers, classes, assignments, results in own dept |
| **Exam Controller** | Exams, students (by roll no), results |
| **Accountant** | Students (by name/roll), fee accounts, receipts |
| **Librarian** | Books by title/author/ISBN, borrowers |
| **Placement Officer** | Students, companies, drives |
| **HR Manager** | Staff by name/employee code, leave records |
| **Admission Officer** | Applications by name/email/application no |

**Task ID:** C-RB-17

---

### PAGE 18 — Calendar `/calendar`✅

**One URL. Events differ per role.**

| Role | Events Shown |
|---|---|
| **Teacher** | Own teaching periods, exam dates, assignment due dates, holidays |
| **Student** | Own class timetable, exam dates, assignment deadlines, holidays, hostel leave dates |
| **Parent** | Child's exam dates, school holidays, fee due dates |
| **Exam Controller** | All exam schedules, result publication dates |
| **Academic Coordinator** | Full academic calendar: timetable, exams, events, holidays |
| **HOD** | Dept exam schedule, dept events, teacher leaves |
| **HR Manager** | Staff leave calendar, appraisal cycle dates, payroll schedule |
| **Placement Officer** | Drive dates, interview schedules, offer deadlines |

**Task ID:** C-RB-18

---

### PAGE 19 — Mentee/Student Detail `/students/:id`✅

**One URL. Different tabs and data visible per role.**

| Role | Tabs Visible | Actions |
|---|---|---|
| **Institution Admin** | Profile · Attendance · Results · Assignments · Fee · Enrollment history | Full edit |
| **Principal / VP** | Profile · Attendance · Results | View only |
| **HOD** | Profile · Attendance (dept) · Results (dept) | View only |
| **Teacher** | Attendance (own subject) · Assignment submissions | View only |
| **Mentor** | Profile · Guardians · Attendance · Results · Coursework · Leave · Notes (private, or shared with co-mentors) | Add / edit / delete own mentor notes (`/mentor/mentees/{id}`) |
| **Exam Controller** | Results · Exam attempts · Malpractice flags | View only |
| **Accountant** | Fee account · Payment history | Record payment |
| **Placement Officer** | Profile · Academic records · Applications · Offers | View + shortlist |
| **HR Manager** | Not applicable — HR manages staff, not students | — |
| **Librarian** | Issued books · Overdue books · Fine history | Issue/return |
| **Hostel Warden** | Room allotment · Hostel attendance · Leave requests | Manage allotment |
| **Transport Manager** | Route assignment · Stop details | Update route |
| **Admission Officer** | Application · Documents · Enrollment status | Enroll student |

**Task ID:** C-RB-19

---

### PAGE 20 — Staff Detail `/staff/:id`✅

**One URL. Different tabs per role.**

| Role | Tabs Visible | Actions |
|---|---|---|
| **Institution Admin** | Profile · Roles · Subjects taught · Leave history | Edit profile, manage roles |
| **Principal / VP** | Profile · Attendance · Leave history | View only |
| **HOD** | Profile · Subjects · Attendance (own dept) | View only |
| **HR Manager** | Full HR profile: banking · Salary · Leave balance · Payslips · Documents · Appraisals | Full HR edit |

**Task ID:** C-RB-20

---

### PAGE 21 — Exam Detail `/examination/:id`✅

**One URL. Three completely different experiences.**

| Role | What They See | Actions |
|---|---|---|
| **Teacher** | Question list editor, exam settings, submission stats, grade descriptive | Edit (if DRAFT), publish, grade answers, release results |
| **Exam Controller** | Exam metadata, hall allocation, submission count, malpractice flags | Allocate halls, compile results, publish |
| **Student** | Exam attempt interface (full screen, timed) OR result view (if completed) | Start attempt, answer questions, submit |
| **HOD / Principal** | Exam details, submission summary, result summary | View only |

**Task ID:** C-RB-21

---

### PAGE 22 — Assignment Detail `/assignments/:id`✅

**One URL. Two experiences.**

| Role | What They See | Actions |
|---|---|---|
| **Teacher** | Assignment info, milestone list, submission table per student | Edit milestones, review submissions, approve/reject |
| **Student** | Assignment instructions, file upload, milestone progress stepper, submission status | Submit files, view feedback, resubmit |
| **HOD** | Overview of submissions, completion rate | View only |

**Task ID:** C-RB-22

---

### PAGE 23 — Hostel Detail `/hostel/rooms/:id`✅

**One URL. Different view for warden vs. student.**

| Role | What They See | Actions |
|---|---|---|
| **Hostel Warden** | Room info, bed occupants list, attendance history, complaints for this room | Edit allotment, mark attendance, resolve complaints |
| **Student** | Own room info, roommates (names only), warden contact | View only |
| **Parent** | Child's room info, block name, warden contact | View only |

**Task ID:** C-RB-23

---

### PAGE 24 — Library Book Detail `/library/books/:id`✅

**One URL. Different actions.**

| Role | What They See | Actions |
|---|---|---|
| **Librarian** | Book title, all copies + accession numbers, full issue history, current borrowers | Issue, return, mark damaged/lost, edit book details |
| **Student / Staff** | Book title, availability count, location code | View only (no issue from here — goes through librarian) |

**Task ID:** C-RB-24

---

## Summary Table — All 24 Role-Based Shared Pages

| # | Page | Route | Roles Using It | Task ID | Backend |
|---|---|---|---|---|---|
| 1 | Dashboard | `/dashboard` | All 17 institution roles | C-RB-01 | Dev-B |
| 2 | Notice Board | `/notices` | All roles (post scope varies) | C-RB-02 | Dev-B |
| 3 | Discussion Forum | `/discussion` | HOD, Teacher, Student, Principal, VP, Coordinator, Mentor | C-RB-03 | Dev-B |
| 4 | Profile Page | `/profile` | All roles | C-RB-04 | Dev-A |
| 5 | Attendance | `/attendance` | Teacher, HOD, Principal, VP, Exam Controller, Student, Parent, Coordinator | C-RB-05 | Dev-B |
| 6 | Examination | `/examination` | Teacher, Exam Controller, HOD, Principal, VP, Coordinator, Student, Parent | C-RB-06 | Dev-B |
| 7 | Assignments | `/assignments` | Teacher, HOD, Principal, VP, Student, Parent | C-RB-07 | Dev-B |
| 8 | Content | `/content` | Teacher, HOD, Principal, Student, Parent | C-RB-08 | Dev-B |
| 9 | Results | `/results` | Teacher, Exam Controller, HOD, Principal, VP, Student, Parent | C-RB-09 | Dev-B |
| 10 | Timetable | `/timetable` | Coordinator, Teacher, HOD, Principal, VP, Student, Parent | C-RB-10 | Dev-B |
| 11 | Fee Account | `/fees` | Accountant, Institution Admin, Student, Parent, Principal | C-RB-11 | Dev-B |
| 12 | User Directory | `/users` | Institution Admin, HOD, Principal, VP, HR Manager, Placement Officer, Admission Officer | C-RB-12 | Dev-A |
| 13 | Leave Management | `/leaves` | Student, Teacher, HOD, Staff, HR Manager, Hostel Warden | C-RB-13 | Dev-B |
| 14 | Reports | `/reports` | All management roles (Admin, Principal, HOD, Teacher, Exam Controller, Accountant, Placement, HR, Transport, Librarian, Store) | C-RB-14 | Dev-B |
| 15 | Notifications | `/notifications` | All roles | C-RB-15 | Dev-A |
| 16 | Settings | `/settings` | All roles (sections vary) | C-RB-16 | Dev-A |
| 17 | Global Search | `/search` | All roles | C-RB-17 | Dev-A+B |
| 18 | Calendar | `/calendar` | Teacher, Student, Parent, Exam Controller, Coordinator, HOD, HR Manager, Placement Officer | C-RB-18 | Dev-B |
| 19 | Student Detail | `/students/:id` | Admin, Principal, VP, HOD, Teacher, Mentor, Exam Controller, Accountant, Placement, Librarian, Warden, Transport, Admission | C-RB-19 | Dev-A+B |
| 20 | Staff Detail | `/staff/:id` | Admin, Principal, VP, HOD, HR Manager | C-RB-20 | Dev-A+B |
| 21 | Exam Detail | `/examination/:id` | Teacher, Exam Controller, Student, HOD, Principal | C-RB-21 | Dev-B |
| 22 | Assignment Detail | `/assignments/:id` | Teacher, Student, HOD | C-RB-22 | Dev-B |
| 23 | Hostel Room Detail | `/hostel/rooms/:id` | Hostel Warden, Student, Parent | C-RB-23 | Dev-B |
| 24 | Library Book Detail | `/library/books/:id` | Librarian, Student, Staff | C-RB-24 | Dev-B |

---

## Implementation Pattern for Dev-C

### Folder Structure

```
apps/web/
└── app/
    └── (institution)/
        ├── dashboard/
        │   └── page.tsx                 ← single file, renders role-based component
        ├── notices/
        │   └── page.tsx                 ← single file, role-aware render
        ├── discussion/
        │   └── page.tsx
        ├── attendance/
        │   └── page.tsx
        ├── examination/
        │   ├── page.tsx
        │   └── [id]/
        │       └── page.tsx
        ├── assignments/
        │   ├── page.tsx
        │   └── [id]/
        │       └── page.tsx
        └── ...

└── components/
    ├── dashboards/              ← 17 dashboard components
    │   ├── TeacherDashboard.tsx
    │   ├── StudentDashboard.tsx
    │   └── ...
    ├── attendance/              ← role-based attendance views
    │   ├── TeacherAttendanceView.tsx
    │   ├── StudentAttendanceView.tsx
    │   └── ...
    ├── examination/             ← role-based exam views
    │   ├── TeacherExamView.tsx
    │   ├── StudentExamAttemptView.tsx
    │   └── ...
    └── shared/                  ← shared UI primitives used across all role views
        ├── RoleGuard.tsx        ← hide/show based on role
        ├── PermissionGuard.tsx  ← hide/show based on permission
        └── ScopeGuard.tsx       ← hide/show based on data scope
```

### Reusable Guards

```typescript
// Show content only to specific roles
<RoleGuard roles={['TEACHER', 'HOD']}>
  <MarkAttendanceButton />
</RoleGuard>

// Show content only if user has permission
<PermissionGuard module="attendance" action="CREATE">
  <MarkAttendanceButton />
</PermissionGuard>

// Show content if module is enabled for this institution
<ModuleGuard module="hostel">
  <HostelTab />
</ModuleGuard>
```

---

## Updated Total Page Count

| Type | Count |
|---|---|
| Role-specific pages (unique per role, from previous doc) | 187 pages |
| Role-based shared pages (one URL, multiple role views) | 24 pages |
| **Grand Total** | **211 pages** |

> The 24 role-based shared pages are already **included** in the 211 count from the previous document.  
> This document explains HOW they differ per role so Dev-C can build them correctly.

---

*Document version: 1.0*  
*24 shared role-based pages · 17 roles use the dashboard · Dev-C builds all role views*  
*Companion: Complete Webpage Developer Assignment · Team Project Plan · Role-Based System Design*

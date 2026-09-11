# ERP + LMS Platform — Role-Based System Design

---

## 1. Platform Overview

```
shikshasync.me  (Multi-Tenant SaaS)
│
├── Platform Layer      → Super Admin controls
└── Institution Layer   → Each college / school is an isolated tenant
```

Each institution activates only the modules it needs. All data is strictly isolated per tenant. Role permissions are enforced at both API gateway and UI level.

---

## 2. Full Role Hierarchy

### 2.1 Platform Level

```
Super Admin
├── Support Staff
├── Sales Executive
└── Finance Manager
```

| Role | Responsibility |
|---|---|
| Super Admin | Full platform control, tenant management, billing, global config |
| Support Staff | Handle institution tickets, impersonate (read-only) for debugging |
| Sales Executive | Manage leads, trial accounts, subscription upgrades |
| Finance Manager | Invoices, subscription plans, payment reconciliation |

---

### 2.2 Institution Level — Core Roles

```
Institution Admin
│
├── Principal
│   └── Vice Principal (optional)
│
├── HOD (Head of Department)
│   ├── Teacher
│   ├── Mentor (optional)
│   └── Academic Coordinator
│
├── Examination Controller
├── Accountant
├── Librarian
├── Student
│   └── Parent (school-type institutions only)
│
└── Optional Module Roles (enabled per institution settings)
    ├── Hostel Warden
    ├── Transport Manager
    ├── Placement Officer
    ├── HR Manager
    ├── Admission Officer
    └── Store Manager
```

---

## 3. Institution Settings — Module Toggle System

When an Institution Admin goes to **Settings → Modules**, they see a checklist of available modules. Enabling a module:

1. Activates the module's UI across the institution
2. Creates the associated role (if optional, e.g., Hostel Warden)
3. Adds the role to the institution's role assignment panel

```
Institution Admin → Settings → Modules

Core Modules (always on):
  ☑ Attendance
  ☑ Examination
  ☑ Assignment & Milestone Tasks
  ☑ Notice Board
  ☑ Discussion Forum
  ☑ Content / Notes Upload
  ☑ Results & Analytics
  ☑ Timetable

Optional Modules (toggle on/off):
  ☐ Library          → activates Librarian role
  ☐ Hostel           → activates Hostel Warden role
  ☐ Transport        → activates Transport Manager role
  ☐ Placement        → activates Placement Officer role
  ☐ HR               → activates HR Manager role
  ☐ Admission        → activates Admission Officer role
  ☐ Inventory        → activates Store Manager role
```

When a module is toggled **off**, its associated roles lose access immediately. Data is retained (not deleted) and restores when re-enabled.

---

## 4. Role Definitions & Permissions

### 4.1 Platform Roles

#### Super Admin
- Create / suspend / delete institutions
- Configure subscription plans
- Access all institution data (audit-only, no edit)
- Manage platform-level Support, Sales, Finance staff
- View global analytics dashboard

#### Support Staff
- View institution data in read-only mode (for debugging)
- Respond to support tickets
- Cannot modify institution data or settings

#### Sales Executive
- Manage trial institution accounts
- Upgrade / downgrade subscription plans
- Cannot access institution academic data

#### Finance Manager
- Generate and view invoices
- Reconcile payments
- Manage pricing plans
- Cannot access institution academic data

---

### 4.2 Institution Admin

The highest role within an institution tenant.

**Access:** Full control over the institution

| Area | Permissions |
|---|---|
| Departments | Create, edit, delete |
| Users | Create all roles, assign, deactivate |
| Modules | Enable / disable optional modules |
| Academic Year | Create, set active year |
| Timetable | Configure master timetable |
| Fee Structure | Define fee heads, installments |
| Notices | Post institution-wide notices |
| Reports | View all analytics and reports |
| Settings | Institution profile, branding, integrations |

---

### 4.3 Principal

**Scope:** Institution-wide (academic authority)

| Area | Permissions |
|---|---|
| Departments | View all |
| Attendance | View institution-level reports |
| Examination | Approve exam schedules |
| Results | View and approve results |
| Notices | Post institution-wide and department notices |
| Staff | View all staff profiles |
| Reports | View all academic reports |
| Timetable | View and request changes |

**Cannot:** Manage fees, billing, or module settings.

#### Vice Principal (optional)
Same as Principal but with scope limited to duties delegated by Principal. Cannot approve final results.

---

### 4.4 HOD (Head of Department)

**Scope:** Own department only

| Area | Permissions |
|---|---|
| Teachers | View, assign subjects |
| Mentors | Assign students to mentors |
| Attendance | View department attendance reports |
| Examination | Create department exam schedule |
| Results | View department results |
| Notices | Post to own department |
| Discussion | Moderate department forum |
| Timetable | View own department timetable |
| Assignments | View all department assignments |
| Reports | Department-level analytics |

---

### 4.5 Teacher

**Scope:** Assigned classes and subjects only

| Module | Permissions |
|---|---|
| Attendance | Mark present/absent/late for own classes |
| Examination | Create exams and quizzes for own subjects |
| Assignment | Create assignments, milestone tasks |
| Grading | Grade submissions, release results |
| Content Upload | Upload notes, videos, slides per subject/chapter |
| Notice Board | Post to assigned classes |
| Discussion | Create threads, reply, moderate own threads |
| Results | View and publish own subject results |
| Timetable | View own schedule |
| Student Profile | View basic profile of own students |

**Cannot:** Edit other teachers' content, view other departments, access fee or ERP data.

#### Mentor (optional)
A teacher-level role scoped to assigned mentee students only.

| Area | Permissions |
|---|---|
| Attendance | View mentee attendance |
| Results | View mentee results |
| Student Profile | View and add notes to mentee profiles |
| Notices | Receive notices for mentee students |
| Discussion | Participate in mentee group forum |

#### Academic Coordinator

| Area | Permissions |
|---|---|
| Timetable | Create and manage timetable |
| Examination | Schedule exams, allocate halls |
| Attendance | View department-wide reports |
| Notices | Post academic notices |
| Reports | Academic calendar reports |

---

### 4.6 Examination Controller

**Scope:** Examination module across all departments

| Area | Permissions |
|---|---|
| Exam Schedule | Create, edit, publish exam timetable |
| Hall Allocation | Assign exam halls and invigilators |
| Question Papers | Receive and manage sealed question papers |
| Attendance | Manage exam attendance / invigilation |
| Results | Compile and publish results |
| Grade Cards | Generate and release grade cards |
| Malpractice | Log and manage malpractice reports |
| Reports | Examination analytics across institution |

**Cannot:** Access fee, HR, hostel, or transport data.

---

### 4.7 Accountant

**Scope:** Finance module

| Area | Permissions |
|---|---|
| Fee Collection | Record fee payments, receipts |
| Fee Defaulters | View and generate defaulter lists |
| Invoices | Generate fee invoices |
| Scholarships | Apply scholarship/concession to student accounts |
| Payroll | Process staff salary (if HR module active) |
| Reports | Financial summary reports |

**Cannot:** Access academic results, examination, or hostel data.

---

### 4.8 Librarian

*(Requires Library module enabled)*

| Area | Permissions |
|---|---|
| Catalogue | Add, edit, delete book records |
| Issue / Return | Issue books to students/staff, record returns |
| Overdue | View and notify overdue returns |
| Inventory | Manage library inventory |
| E-Resources | Upload digital resources |
| Reports | Library usage reports |

---

### 4.9 Student

**Scope:** Own data only

| Module | Permissions |
|---|---|
| Attendance | View own attendance record |
| Timetable | View own class timetable |
| Examination | View exam schedule, attempt online exams/quizzes |
| Assignments | View, download, submit assignments and milestone stages |
| Content | Download notes and study materials |
| Results | View own results and grade cards |
| Notice Board | View notices relevant to own class/department |
| Discussion | Post questions, reply, upvote threads |
| Library | Search catalogue, view issued books (if module active) |
| Hostel | View own room and fee details (if applicable) |
| Transport | View own bus route (if applicable) |
| Placement | View opportunities, submit profile (if applicable) |

**Cannot:** View other students' data, mark attendance, create exams.

#### Parent (school-type only)

| Area | Permissions |
|---|---|
| Attendance | View child's attendance |
| Results | View child's results and grade cards |
| Notice Board | View school and class notices |
| Fee | View child's fee status and dues |
| Timetable | View child's timetable |
| Hostel | View child's hostel details (if applicable) |
| Transport | View child's bus route and stop (if applicable) |

**Cannot:** Post notices, access other students' data, edit any records.

---

## 5. Optional Module Roles

### 5.1 Hostel Warden *(Hostel module)*

| Area | Permissions |
|---|---|
| Room Allotment | Assign students to rooms |
| Attendance | Mark hostel attendance |
| Fees | View hostel fee status |
| Complaints | Manage student complaints |
| Leave | Approve/reject student leave requests |
| Notices | Post hostel notices |
| Reports | Occupancy and attendance reports |

---

### 5.2 Transport Manager *(Transport module)*

| Area | Permissions |
|---|---|
| Routes | Create and manage bus routes and stops |
| Vehicles | Manage vehicle records |
| Driver / Attendant | Manage driver profiles |
| Students | Assign students to routes |
| Fees | View transport fee status |
| Tracking | Live GPS tracking (if integrated) |
| Reports | Route utilization reports |

---

### 5.3 Placement Officer *(Placement module)*

| Area | Permissions |
|---|---|
| Companies | Add and manage company profiles |
| Job Postings | Post placement opportunities |
| Applications | Track student applications |
| Eligibility | Set eligibility criteria per drive |
| Interviews | Schedule and record interview rounds |
| Offers | Record and publish offer letters |
| Reports | Placement statistics and reports |

---

### 5.4 HR Manager *(HR module)*

| Area | Permissions |
|---|---|
| Staff Records | Create and manage all staff profiles |
| Leave | Manage leave policies and approvals |
| Payroll | Process salary, generate payslips |
| Attendance | View staff attendance |
| Appraisals | Manage performance appraisal cycles |
| Documents | Manage staff documents (contracts, certificates) |
| Reports | HR analytics and headcount reports |

---

### 5.5 Admission Officer *(Admission module)*

| Area | Permissions |
|---|---|
| Applications | Receive and process admission applications |
| Enquiries | Manage enquiry leads |
| Documents | Collect and verify student documents |
| Merit List | Generate and publish merit lists |
| Enrollment | Convert admitted students to enrolled users |
| Reports | Admission funnel and conversion reports |

---

### 5.6 Store Manager *(Inventory module)*

| Area | Permissions |
|---|---|
| Items | Add and manage inventory items |
| Stock In | Record new stock arrivals |
| Stock Out | Issue items to departments/staff |
| Low Stock | View and alert on low stock items |
| Vendors | Manage vendor records |
| Purchase Orders | Create and track purchase orders |
| Reports | Stock utilization reports |

---

## 6. Permission Matrix Summary

| Role | Attendance | Examination | Assignment | Notice Board | Discussion | Content | Results | Finance | HR | Optional Modules |
|---|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| Super Admin | ● read | ● read | ● read | ● read | ● read | ● read | ● read | ● full | ● full | ● full |
| Institution Admin | ● full | ● full | ● full | ● full | ● full | ● full | ● full | ● full | ● full | ● config |
| Principal | ● view | ● approve | ● view | ● post | ● view | ● view | ● approve | — | — | ● view |
| Vice Principal | ● view | ● view | ● view | ● post | ● view | ● view | ● view | — | — | ● view |
| HOD | ● dept | ● dept | ● dept | ● dept | ● moderate | ● dept | ● dept | — | — | — |
| Teacher | ● mark | ● create | ● create | ● class | ● post | ● upload | ● publish | — | — | — |
| Mentor | ● view | ● view | ● view | ● view | ● post | ● view | ● view | — | — | — |
| Academic Coordinator | ● view | ● schedule | — | ● post | — | — | — | — | — | — |
| Exam Controller | ● exam | ● full | — | ● post | — | — | ● compile | — | — | — |
| Accountant | — | — | — | ● view | — | — | — | ● full | ● payroll | — |
| Librarian | — | — | — | ● view | — | ● library | — | — | — | ● library |
| Student | ● own | ● attempt | ● submit | ● view | ● post | ● download | ● own | — | — | ● own |
| Parent | ● child | — | ● view | ● view | — | — | ● child | ● fees | — | ● child |

> ● full = full CRUD | ● view / read = read only | ● own / child / dept / class = scoped access | — = no access

---

## 7. Module Activation Flow

```
Institution Admin
       │
       ▼
Settings → Modules
       │
       ├── Toggle Module ON
       │        │
       │        ├── Module becomes visible in navigation
       │        ├── Associated role is created in the system
       │        ├── Institution Admin can now assign users to that role
       │        └── Role permissions become active immediately
       │
       └── Toggle Module OFF
                │
                ├── Module hidden from all users
                ├── Role access revoked
                ├── Data retained (not deleted)
                └── Restores fully on re-enable
```

---

## 8. Multi-Tenancy & Data Isolation Rules

1. **Tenant ID** is injected at the API gateway on every request. All database queries are scoped to the tenant automatically.
2. **No cross-tenant data access** is possible at any role level, including Super Admin (audit read-only via a separate controlled view).
3. **Module flags** are stored per tenant. Disabling a module sets `module.active = false` — data persists in its schema.
4. **Role assignments** exist only within the tenant. A teacher at ABC College cannot appear in XYZ College's system.
5. **Academic Year scoping**: All records (attendance, results, assignments) are linked to the active academic year. Historical years are accessible in read-only archive mode.

---

## 9. Key Implementation Notes

### Role Inheritance
Roles do **not** inherit from each other automatically. Each role has an explicit permission set. If a user holds multiple roles (e.g., a teacher who is also a mentor), permissions are **merged (union)** — the user gets the highest permission for each area.

### Scoped Access Pattern
Scopes narrow what data a role can see:

| Scope Level | Applied to |
|---|---|
| Institution | Principal, Vice Principal, Exam Controller, Accountant |
| Department | HOD, Academic Coordinator |
| Class / Subject | Teacher |
| Mentee Group | Mentor |
| Self | Student |
| Own child | Parent |

### Audit Trail
Every write action (create, update, delete) by any role is logged with:
- `user_id`, `role`, `tenant_id`
- `action`, `entity`, `entity_id`
- `timestamp`, `ip_address`

Super Admin and Institution Admin can view audit logs. Others cannot.

---

## 10. Suggested Database Tables

```
tenants               id, name, type (school|college), plan, active_modules[]
users                 id, tenant_id, name, email, password_hash
roles                 id, name, scope_level, module
role_assignments      user_id, role_id, tenant_id, scope_id (dept/class/subject)
modules               id, name, is_core, description
tenant_modules        tenant_id, module_id, enabled, enabled_at, enabled_by
permissions           role_id, module_id, action (create|read|update|delete), scope
audit_logs            id, tenant_id, user_id, action, entity, entity_id, timestamp
```

---

*Document version: 1.0 | For: shikshasync.me ERP + LMS Platform*

# Institution Admin — Simple User Guide

This guide is for the person who runs the institution on shikshasync.me — the principal,
the office administrator, or whoever was given the **Institution Admin** role.
You do not need to be technical. Read this once and you will know how to run
your school or college on the platform.

---

## What is the "Admin Console"?

It is your control room. After you sign in, everything about your institution —
classes, staff, students, modules, settings — is managed from one place, at:

```
https://<your-institution>.shikshasync.me/admin/dashboard
```

For example, Green College's admin works at `green.shikshasync.me/admin/dashboard`.

Only people with the **Institution Admin** role can open it. Everyone else is
sent to the normal login screen.

---

## Step 0 — How to sign in

1. Open your institution's login page, e.g. `https://green.shikshasync.me/login`.
2. Enter your **email** and **password** (given to you by the platform team or
   set from your invite email).
3. You will land on the **Dashboard**.

If you forgot your password, use the **Forgot password?** link on the login page.

---

## The menu (left side)

| Menu item | What you do there |
|---|---|
| **Dashboard** | See numbers: how many students, staff, departments, classes, etc. |
| **Academic Years** | Add the years your institution runs (e.g. 2026–27). |
| **Departments** | Add departments (e.g. Computer Science, Commerce). |
| **Staff** | Add teachers and other staff; give them roles. |
| **Students** | Add students and enrol them into classes. |
| **Modules** | Turn extra features on or off. |
| **Settings** | Change timezone and currency. |
| **Profile** | Update your institution's name, address, logo, contact. |

On a phone, open the menu with the ☰ button at the top left.

---

## Step 1 — Set your Academic Year

Before you add classes or students, you need **one current academic year**.

1. Go to **Academic Years**.
2. Fill in: a name (e.g. `2026-27`), a start date and an end date.
3. Tick **Set as current year** for the year that is happening right now.
4. Click **Add year**.

> Only **one** year can be "current" at a time. If you mark a new one as current,
> the old one automatically stops being current. You cannot delete the current
> year — switch current to another year first.

---

## Step 2 — Create Departments

A department is a section of your institution (Computer Science, Commerce,
Arts, Primary School…).

1. Go to **Departments**.
2. Type a **Name** (e.g. `Computer Science & Engineering`) and a short **Code**
   (e.g. `CSE`).
3. Click **Add department**.

Each department card shows how many classes and staff belong to it. You can
delete a department only when it has no classes left in it.

When you select a department **HOD**, the platform also creates that person’s
HOD department scope automatically. That is what lets them open the HOD console
and see only their own classes, teachers, students and academic work.

---

## Step 3 — Add Staff (teachers and team)

1. Go to **Staff** and click **Invite**.
2. Enter the person's **name, email, phone** and pick a **role**
   (Teacher, Principal, HOD, Accountant, …).
3. If the role is **Vice Principal**, choose their **delegated department**.
   A Vice Principal can only see attendance, exams, results, staff and notices
   for delegated departments; leaving this blank is intentionally blocked.
4. Click **Send invite**.

**Adding many staff at once:** click **Bulk upload**, download the CSV
template, fill in your team and upload the file. Headers: `name`, `email`,
`role` (required), `phone`, `department_code` (optional — the department code,
e.g. `CS`, scopes roles like HOD and is required for Vice Principal). The page
reports how many were imported and lists any failed rows with their row
numbers, so you can fix and re-upload just those. Every imported member
receives the same set-password invite email.

What happens next:
- The person gets an **email with a "set your password" link**.
- They set their own password and can sign in.
- **You never see their password** — that is by design, for safety.

To give someone an **extra role** later (for example, make a Teacher also a
Mentor), find them in the list and click the small role buttons under their name
(`+ teacher`, `+ hod`, …).

For a **Vice Principal**, use the **Delegate VP department** selector on their
staff card. Select a department and choose **Assign VP role** or **Add
department**. To remove one delegation, select that department and choose
**Revoke selected scope**. Removing one scope does not remove their other
assigned departments. If you remove the last scope, that person can no longer
open the Vice Principal console.

---

## Step 4 — Add Students

Students are added by the institution from the **Students** page — one by one,
or all at once with a CSV upload.

1. Make sure you have an **Academic Year** and a **Class** ready first.
2. **One by one:** click **Add student** and create the student with a
   **roll number** (unique for your institution) and, if you like, an email.
3. **Bulk upload:** click **Bulk upload**, download the CSV template, fill in
   your students and upload the file. The page then reports how many students
   were imported and lists any rows that failed (e.g. duplicate roll numbers)
   with their row numbers, so you can fix and re-upload just those.
   - Headers: `name`, `roll_no` (required), `email`, `gender`,
     `date_of_birth`, `class_code` (optional).
   - Use the class **code** (e.g. `PHY-1`) to enrol students automatically.
4. When you add a student you can also **enrol** them straight into a class for
   the current year. To enrol an existing student later, click **Enrol** next
   to their name.
5. All current enrolments are listed at the bottom of the **Students** page.

> Two students cannot share the same roll number in your institution.

---

## Step 5 — Turn features on or off (Modules)

Go to **Modules**. You will see all available features.

- **Core modules** (Attendance, Examinations, Assignments, Notices, Discussions,
  Content, Results, Timetable) are **always on** — you cannot switch them off.
- **Optional modules** (Library, Hostel, Transport, HR, …) have a toggle.
  - Switch one **on** if your plan includes it.
  - If a toggle does not turn on and you see a message about your **plan**, it
    means that module is not in your subscription. Ask the account owner to
    upgrade the plan.

> The person who owns the shikshasync.me **account** (the one who pays the bill) manages
> plans and billing from their own dashboard at `shikshasync.me` — that is a separate
> login from this admin console.

---

## Step 6 — Update your institution details

- **Profile**: change your institution's name, address, city, phone, website and
  logo. These show to your staff and students.
- **Settings**: set your **timezone** (so dates and times are correct) and
  **currency** (for fees and reports). In India this is usually `Asia/Kolkata`
  and `INR`.

Click **Save** after editing.

---

## Day-to-day, in one line

> **Dashboard** to check numbers → **Academic Years / Departments / Staff /
> Students** to keep records correct → **Modules** to switch features on or off →
> **Settings / Profile** to keep details up to date.

---

## Frequently asked questions

**I see "Institution admin privileges are required."**
You signed in with an account that is not an admin. Sign out and sign in with
the admin account, or ask the current admin to give you the role.

**A staff member did not get the invite email.**
Ask them to check spam. If still missing, the platform team can resend it from
the database, or you can invite them again with the same email.

**Can two institutions share one login?**
No. Each institution has its own secure login at its own address
(`green.shikshasync.me`, `abc-school.shikshasync.me`). But the **owner account** at `shikshasync.me`
can manage and pay for several institutions from one place.

**I made a mistake — can I delete things?**
Yes for academic years (not the current one), departments (only if empty), and
you can deactivate staff. Students and classes can be removed by your platform
team if needed.

**Something is broken. Who do I call?**
Use **Support Tickets** from the owner dashboard (`shikshasync.me`), or contact your
platform team. Describe what you did and what you saw.

---

_This guide covers the live admin features. As more module pages (attendance,
exams, fees, library, …) are connected, they will appear in the same menu with
the same simple pattern._

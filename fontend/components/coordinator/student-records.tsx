"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Check,
  Edit2,
  FileSpreadsheet,
  Filter,
  Mail,
  Plus,
  Search,
  Trash2,
  Upload,
  UserCheck,
  UserX,
  Users,
  X,
} from "lucide-react";

import { Card, EmptyState, ErrorState, inputClass, labelClass, Loading, PageHeader } from "@/components/admin/ui";
import {
  createStudent,
  deleteStudent,
  fetchClasses,
  fetchStudents,
  resendPasswordReset,
  resendStudentPasswordReset,
  updateStudent,
  uploadStudents,
  type BulkUploadResult,
  type ClassRecord,
  type StudentRecord,
} from "@/lib/institution";

const SAMPLE_CSV = [
  "name,roll_no,email,gender,class_code,password",
  "Aarav Sharma,CS101,aarav@school.edu,MALE,10-A,SecurePass1!",
  "Ananya Patel,CS102,ananya@school.edu,FEMALE,10-A,",
].join("\n");

export function StudentRecordsPage({ isAdmin = false }: { isAdmin?: boolean }) {
  const [students, setStudents] = useState<StudentRecord[] | null>(null);
  const [classes, setClasses] = useState<ClassRecord[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [showBulk, setShowBulk] = useState(false);
  const [busy, setBusy] = useState(false);
  const [search, setSearch] = useState("");
  const [classFilter, setClassFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState<"ALL" | "ACTIVE" | "INACTIVE">("ALL");

  // Add Form state
  const [form, setForm] = useState({ name: "", roll_no: "", email: "", gender: "", class_id: "", password: "" });

  // Edit Modal state
  const [editingStudent, setEditingStudent] = useState<StudentRecord | null>(null);
  const [editForm, setEditForm] = useState({ name: "", roll_no: "", email: "", gender: "", class_id: "", is_active: true });
  const [editBusy, setEditBusy] = useState(false);

  // Bulk Upload state
  const [bulkFile, setBulkFile] = useState<File | null>(null);
  const [bulkResult, setBulkResult] = useState<BulkUploadResult | null>(null);
  const [bulkBusy, setBulkBusy] = useState(false);
  const [resettingStudentId, setResettingStudentId] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const [studentRows, classRows] = await Promise.all([fetchStudents(), fetchClasses()]);
      setStudents(studentRows);
      setClasses(classRows.filter((row) => row.is_active));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load student records.");
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  // Filtered Students
  const filteredStudents = useMemo(() => {
    if (!students) return [];
    return students.filter((s) => {
      const matchesSearch =
        !search ||
        s.name.toLowerCase().includes(search.toLowerCase()) ||
        (s.roll_no && s.roll_no.toLowerCase().includes(search.toLowerCase())) ||
        (s.email && s.email.toLowerCase().includes(search.toLowerCase()));

      const matchesClass =
        !classFilter ||
        (s.enrollment?.class_id === classFilter);

      const matchesStatus =
        statusFilter === "ALL" ||
        (statusFilter === "ACTIVE" && s.is_active) ||
        (statusFilter === "INACTIVE" && !s.is_active);

      return matchesSearch && matchesClass && matchesStatus;
    });
  }, [students, search, classFilter, statusFilter]);

  async function addStudent(event: React.FormEvent) {
    event.preventDefault();
    if (!form.name || !form.roll_no) return;
    setBusy(true);
    setError(null);
    try {
      await createStudent({
        name: form.name,
        roll_no: form.roll_no,
        email: form.email || undefined,
        gender: form.gender || undefined,
        class_id: form.class_id || undefined,
        password: form.password || undefined,
      });
      setForm({ name: "", roll_no: "", email: "", gender: "", class_id: "", password: "" });
      setAdding(false);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not add the student.");
    } finally {
      setBusy(false);
    }
  }

  function startEdit(student: StudentRecord) {
    setEditingStudent(student);
    setEditForm({
      name: student.name,
      roll_no: student.roll_no || "",
      email: student.email || "",
      gender: student.gender || "",
      class_id: student.enrollment?.class_id || "",
      is_active: student.is_active,
    });
    setError(null);
  }

  async function saveEdit(event: React.FormEvent) {
    event.preventDefault();
    if (!editingStudent || !editForm.name || !editForm.roll_no) return;
    setEditBusy(true);
    setError(null);
    try {
      await updateStudent(editingStudent.id, {
        name: editForm.name,
        roll_no: editForm.roll_no,
        email: editForm.email || undefined,
        gender: editForm.gender || undefined,
        class_id: editForm.class_id || undefined,
        is_active: editForm.is_active,
      });
      setEditingStudent(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update student.");
    } finally {
      setEditBusy(false);
    }
  }

  async function toggleStatus(student: StudentRecord) {
    setError(null);
    try {
      await updateStudent(student.id, { is_active: !student.is_active });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update status.");
    }
  }

  async function handleDelete(student: StudentRecord) {
    if (!confirm(`Are you sure you want to delete ${student.name}?`)) return;
    setError(null);
    try {
      await deleteStudent(student.id);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete student.");
    }
  }

  async function sendPasswordReset(student: StudentRecord) {
    if (!student.email) {
      setError("This student has no email address for a password reset link.");
      return;
    }
    setResettingStudentId(student.id);
    setError(null);
    try {
      await (isAdmin
        ? resendPasswordReset(student.id)
        : resendStudentPasswordReset(student.id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not send the password reset link.");
    } finally {
      setResettingStudentId(null);
    }
  }

  async function handleBulkUpload(event: React.FormEvent) {
    event.preventDefault();
    if (!bulkFile) return;
    setBulkBusy(true);
    setError(null);
    setBulkResult(null);
    try {
      const res = await uploadStudents(bulkFile);
      setBulkResult(res);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not upload CSV.");
    } finally {
      setBulkBusy(false);
    }
  }

  function downloadSample() {
    const blob = new Blob([SAMPLE_CSV], { type: "text/csv" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "sample_students.csv";
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="mx-auto max-w-6xl space-y-6">
      <PageHeader
        title="Student records"
        subtitle={
          isAdmin
            ? "Manage student accounts, active class enrollments, and status."
            : "Add and manage student accounts, roll numbers, and academic class assignments."
        }
        action={
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => setShowBulk((v) => !v)}
              className="inline-flex h-10 items-center gap-2 rounded-field border border-border bg-white px-4 text-sm font-semibold text-primary shadow-sm hover:bg-muted/40"
            >
              <Upload className="h-4 w-4 text-accent" /> Bulk Import
            </button>
            <button
              type="button"
              onClick={() => setAdding((v) => !v)}
              className="inline-flex h-10 items-center gap-2 rounded-field bg-accent px-4 text-sm font-semibold text-white shadow-accent hover:bg-accent-hover"
            >
              <Plus className="h-4 w-4" /> Add student
            </button>
          </div>
        }
      />

      {/* CSV Bulk Import Section */}
      {showBulk && (
        <Card className="mb-6 border-accent/20 bg-accent-light/10">
          <div className="flex items-center justify-between border-b border-border pb-3 mb-4">
            <div className="flex items-center gap-2">
              <FileSpreadsheet className="h-5 w-5 text-accent" />
              <h3 className="font-display font-bold text-primary">Bulk Student CSV Import</h3>
            </div>
            <button type="button" onClick={() => setShowBulk(false)} className="text-muted-foreground hover:text-foreground">
              <X className="h-4 w-4" />
            </button>
          </div>
          <form onSubmit={handleBulkUpload} className="space-y-4">
            <p className="text-xs text-muted-foreground">
              Required headers: <code className="rounded bg-muted px-1 font-mono">name, roll_no</code>. Optional: <code className="rounded bg-muted px-1 font-mono">email, gender, date_of_birth, class_code, password</code>. Leave password blank to use <code className="rounded bg-muted px-1 font-mono text-primary font-bold">password1232!</code>.
            </p>
            <div className="flex flex-wrap items-center gap-4">
              <input
                type="file"
                accept=".csv"
                required
                onChange={(e) => setBulkFile(e.target.files?.[0] ?? null)}
                className="text-xs text-muted-foreground file:mr-3 file:rounded-lg file:border-0 file:bg-accent file:px-3 file:py-2 file:text-xs file:font-semibold file:text-white hover:file:bg-accent-hover"
              />
              <button
                type="submit"
                disabled={bulkBusy || !bulkFile}
                className="inline-flex h-9 items-center gap-2 rounded-field bg-accent px-4 text-xs font-semibold text-white shadow-sm hover:bg-accent-hover disabled:opacity-60"
              >
                {bulkBusy ? "Uploading…" : "Upload CSV"}
              </button>
              <button
                type="button"
                onClick={downloadSample}
                className="text-xs text-accent underline hover:text-accent-hover"
              >
                Download sample CSV template
              </button>
            </div>
            {bulkResult && (
              <div className="mt-3 rounded-lg border border-accent/30 bg-accent-light/20 p-3 text-xs">
                <p className="font-semibold text-primary">
                  Import Summary: {bulkResult.created} created out of {bulkResult.total} rows.
                </p>
                {bulkResult.errors.length > 0 && (
                  <ul className="mt-2 list-disc pl-4 text-destructive space-y-0.5">
                    {bulkResult.errors.map((err, i) => (
                      <li key={i}>Row {err.row}: {err.message}</li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </form>
        </Card>
      )}

      {/* Add Student Form */}
      {adding && (
        <Card className="mb-6">
          <div className="flex items-center justify-between border-b border-border pb-3 mb-4">
            <div>
              <h3 className="font-display font-bold text-primary">Add New Student</h3>
              <p className="text-xs text-muted-foreground">Leave initial password blank to use <code className="rounded bg-muted px-1 font-mono text-primary font-bold">password1232!</code>.</p>
            </div>
            <button type="button" onClick={() => setAdding(false)} className="text-muted-foreground hover:text-foreground">
              <X className="h-4 w-4" />
            </button>
          </div>
          <form onSubmit={addStudent} className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <div>
              <label className={labelClass}>Full name</label>
              <input required className={inputClass} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Aarav Sharma" />
            </div>
            <div>
              <label className={labelClass}>Roll number</label>
              <input required className={inputClass} value={form.roll_no} onChange={(e) => setForm({ ...form, roll_no: e.target.value })} placeholder="CS101" />
            </div>
            <div>
              <label className={labelClass}>Email (optional)</label>
              <input type="email" className={inputClass} value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="aarav@school.edu" />
            </div>
            <div>
              <label className={labelClass}>Initial password (optional)</label>
              <input type="password" minLength={8} maxLength={128} className={inputClass} value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} placeholder="Leave blank for default" />
            </div>
            <div>
              <label className={labelClass}>Gender (optional)</label>
              <select className={inputClass} value={form.gender} onChange={(e) => setForm({ ...form, gender: e.target.value })}>
                <option value="">Not specified</option>
                <option value="MALE">Male</option>
                <option value="FEMALE">Female</option>
                <option value="OTHER">Other</option>
              </select>
            </div>
            <div>
              <label className={labelClass}>Class / section</label>
              <select className={inputClass} value={form.class_id} onChange={(e) => setForm({ ...form, class_id: e.target.value })}>
                <option value="">Assign later</option>
                {classes.map((row) => (
                  <option key={row.id} value={row.id}>{row.name} ({row.code})</option>
                ))}
              </select>
            </div>
            <div className="flex items-end">
              <button disabled={busy} className="h-11 rounded-field bg-accent px-5 text-sm font-semibold text-white disabled:opacity-60">
                {busy ? "Saving…" : "Save student"}
              </button>
            </div>
          </form>
        </Card>
      )}

      {/* Global Error Banner */}
      {error && (
        <div className="mb-4">
          <ErrorState message={error} />
        </div>
      )}

      {/* Search & Filter Bar */}
      <Card className="!p-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="relative flex-1 min-w-[220px]">
            <Search className="absolute left-3 top-3 h-4 w-4 text-muted-foreground" />
            <input
              type="text"
              placeholder="Search by student name, roll no, or email..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full rounded-lg border border-border bg-background pl-9 pr-3 py-2 text-xs text-foreground outline-none focus:border-accent"
            />
          </div>

          <div className="flex items-center gap-2">
            <Filter className="h-4 w-4 text-muted-foreground" />
            <select
              value={classFilter}
              onChange={(e) => setClassFilter(e.target.value)}
              className="h-9 rounded-lg border border-border bg-background px-3 text-xs text-foreground outline-none focus:border-accent"
            >
              <option value="">All Classes</option>
              {classes.map((c) => (
                <option key={c.id} value={c.id}>{c.name} ({c.code})</option>
              ))}
            </select>

            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value as "ALL" | "ACTIVE" | "INACTIVE")}
              className="h-9 rounded-lg border border-border bg-background px-3 text-xs text-foreground outline-none focus:border-accent"
            >
              <option value="ALL">All Status</option>
              <option value="ACTIVE">Active</option>
              <option value="INACTIVE">Inactive</option>
            </select>
          </div>
        </div>
      </Card>

      {/* Students Table */}
      {students === null ? (
        <Loading />
      ) : students.length === 0 ? (
        <EmptyState text="No student records yet. Add your first student above." />
      ) : filteredStudents.length === 0 ? (
        <Card className="p-8 text-center text-xs text-muted-foreground">
          No students match your search or filter criteria.
        </Card>
      ) : (
        <Card className="overflow-hidden !p-0">
          <div className="flex items-center justify-between border-b border-border px-5 py-4">
            <div className="flex items-center gap-2">
              <Users className="h-5 w-5 text-accent" />
              <h2 className="font-display font-bold text-primary">
                Students ({filteredStudents.length} of {students.length})
              </h2>
            </div>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-sm">
              <thead className="bg-muted text-xs uppercase text-muted-foreground">
                <tr>
                  <th className="px-5 py-3">Student</th>
                  <th className="px-5 py-3">Roll no.</th>
                  <th className="px-5 py-3">Class / section</th>
                  <th className="px-5 py-3">Academic year</th>
                  <th className="px-5 py-3">Status</th>
                  <th className="px-5 py-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border">
                {filteredStudents.map((student) => (
                  <tr key={student.id} className="hover:bg-muted/20 transition-colors">
                    <td className="px-5 py-3">
                      <p className="font-semibold text-primary">{student.name}</p>
                      <p className="text-xs text-muted-foreground">{student.email ?? "No email"}</p>
                    </td>
                    <td className="px-5 py-3 font-mono text-primary">{student.roll_no ?? "—"}</td>
                    <td className="px-5 py-3 text-muted-foreground">
                      {student.enrollment?.class_name ?? "Not assigned"}
                    </td>
                    <td className="px-5 py-3 text-muted-foreground">
                      {student.enrollment?.academic_year_name ?? "—"}
                    </td>
                    <td className="px-5 py-3">
                      <button
                        type="button"
                        onClick={() => toggleStatus(student)}
                        className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] font-semibold transition ${
                          student.is_active
                            ? "bg-emerald-50 text-emerald-700 hover:bg-emerald-100"
                            : "bg-rose-50 text-rose-700 hover:bg-rose-100"
                        }`}
                        title="Click to toggle status"
                      >
                        {student.is_active ? <UserCheck className="h-3 w-3" /> : <UserX className="h-3 w-3" />}
                        {student.is_active ? "Active" : "Inactive"}
                      </button>
                    </td>
                    <td className="px-5 py-3 text-right">
                      <div className="flex items-center justify-end gap-1">
                        <button
                          type="button"
                          onClick={() => startEdit(student)}
                          className="rounded-lg p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground transition-colors"
                          title="Edit student"
                        >
                          <Edit2 className="h-4 w-4" />
                        </button>
                        <button
                          type="button"
                          disabled={!student.is_active || !student.email || resettingStudentId === student.id}
                          onClick={() => sendPasswordReset(student)}
                          className="rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-accent-light hover:text-accent disabled:cursor-not-allowed disabled:opacity-40"
                          title={student.email ? "Send password reset link" : "No email address"}
                        >
                          <Mail className="h-4 w-4" />
                        </button>
                        <button
                          type="button"
                          onClick={() => handleDelete(student)}
                          className="rounded-lg p-1.5 text-muted-foreground hover:bg-destructive-light hover:text-destructive-text transition-colors"
                          title="Delete student"
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      )}

      {/* Edit Student Modal */}
      {editingStudent && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm">
          <div className="w-full max-w-lg rounded-xl border border-border bg-white p-6 shadow-2xl animate-in fade-in zoom-in duration-150">
            <div className="flex items-center justify-between border-b border-border pb-4 mb-4">
              <div>
                <h2 className="font-display text-lg font-bold text-primary">Edit Student Details</h2>
                <p className="text-xs text-muted-foreground">Update student profile, roll number, and class enrollment.</p>
              </div>
              <button type="button" onClick={() => setEditingStudent(null)} className="text-muted-foreground hover:text-foreground">
                <X className="h-5 w-5" />
              </button>
            </div>

            <form onSubmit={saveEdit} className="space-y-4">
              <div>
                <label className={labelClass}>Full name</label>
                <input
                  required
                  className={inputClass}
                  value={editForm.name}
                  onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                />
              </div>

              <div>
                <label className={labelClass}>Roll number</label>
                <input
                  required
                  className={inputClass}
                  value={editForm.roll_no}
                  onChange={(e) => setEditForm({ ...editForm, roll_no: e.target.value })}
                />
              </div>

              <div>
                <label className={labelClass}>Email (optional)</label>
                <input
                  type="email"
                  className={inputClass}
                  value={editForm.email}
                  onChange={(e) => setEditForm({ ...editForm, email: e.target.value })}
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className={labelClass}>Gender</label>
                  <select
                    className={inputClass}
                    value={editForm.gender}
                    onChange={(e) => setEditForm({ ...editForm, gender: e.target.value })}
                  >
                    <option value="">Not specified</option>
                    <option value="MALE">Male</option>
                    <option value="FEMALE">Female</option>
                    <option value="OTHER">Other</option>
                  </select>
                </div>

                <div>
                  <label className={labelClass}>Class / section</label>
                  <select
                    className={inputClass}
                    value={editForm.class_id}
                    onChange={(e) => setEditForm({ ...editForm, class_id: e.target.value })}
                  >
                    <option value="">Unassigned</option>
                    {classes.map((row) => (
                      <option key={row.id} value={row.id}>{row.name} ({row.code})</option>
                    ))}
                  </select>
                </div>
              </div>

              <div className="flex items-center gap-2 pt-2">
                <input
                  type="checkbox"
                  id="edit-student-active"
                  checked={editForm.is_active}
                  onChange={(e) => setEditForm({ ...editForm, is_active: e.target.checked })}
                  className="h-4 w-4 rounded border-border text-accent focus:ring-accent"
                />
                <label htmlFor="edit-student-active" className="text-xs font-semibold text-primary">
                  Active Student Account
                </label>
              </div>

              <div className="flex justify-end gap-2 pt-4 border-t border-border">
                <button
                  type="button"
                  onClick={() => setEditingStudent(null)}
                  className="h-10 rounded-field border border-border px-4 text-xs font-semibold text-muted-foreground hover:bg-muted/40"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={editBusy}
                  className="h-10 rounded-field bg-accent px-5 text-xs font-semibold text-white hover:bg-accent-hover disabled:opacity-60"
                >
                  {editBusy ? "Saving…" : "Save Changes"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

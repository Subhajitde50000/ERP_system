"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  Building2,
  CheckCircle2,
  Download,
  Edit,
  Eye,
  Mail,
  Phone,
  Plus,
  Power,
  Search,
  SlidersHorizontal,
  Trash2,
  Upload,
  UserPlus,
  X,
  XCircle,
} from "lucide-react";

import { Card, EmptyState, ErrorState, inputClass, labelClass, Loading, PageHeader } from "@/components/admin/ui";
import {
  assignStaffRole,
  deleteStaff,
  fetchDepartments,
  fetchStaff,
  inviteStaff,
  revokeStaffRole,
  resendPasswordReset,
  setStaffActive,
  updateStaff,
  uploadStaff,
  type BulkUploadResult,
  type BulkUploadRowIssue,
  type Department,
  type StaffMember,
} from "@/lib/institution";
import { roleLabel, STAFF_INVITABLE_ROLES } from "@/lib/roles";
import type { Role } from "@/types/auth";

const TEMPLATE_CSV = [
  "name,email,phone,role,department_code",
  "Priya Nair,priya@college.edu,+91 98765 43210,TEACHER,CS",
  "Rahul Verma,rahul@college.edu,,ACADEMIC_COORDINATOR,",
].join("\n");

export default function StaffPage() {
  const [staff, setStaff] = useState<StaffMember[] | null>(null);
  const [departments, setDepartments] = useState<Department[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [form, setForm] = useState({
    name: "",
    email: "",
    phone: "",
    role: "TEACHER",
    departmentId: "",
  });
  const [showForm, setShowForm] = useState(false);
  const [vpDepartments, setVpDepartments] = useState<Record<string, string>>({});
  const [showBulk, setShowBulk] = useState(false);
  const [bulkFile, setBulkFile] = useState<File | null>(null);
  const [bulkResult, setBulkResult] = useState<BulkUploadResult | null>(null);
  const [bulkBusy, setBulkBusy] = useState(false);
  const [resettingUserId, setResettingUserId] = useState<string | null>(null);
  const [bulkError, setBulkError] = useState<string | null>(null);
  const bulkInputRef = useRef<HTMLInputElement>(null);

  // Edit Staff Modal State
  const [editMember, setEditMember] = useState<StaffMember | null>(null);
  const [editForm, setEditForm] = useState({
    name: "",
    email: "",
    phone: "",
    departmentId: "",
  });
  const [editBusy, setEditBusy] = useState(false);

  // Details Modal State
  const [detailMember, setDetailMember] = useState<StaffMember | null>(null);

  // Search & Filter State
  const [search, setSearch] = useState("");
  const [filterRole, setFilterRole] = useState("");
  const [filterDepartment, setFilterDepartment] = useState("");
  const [filterStatus, setFilterStatus] = useState<"" | "active" | "inactive">("");

  const load = useCallback(async () => {
    try {
      const [staffRows, departmentRows] = await Promise.all([fetchStaff(), fetchDepartments()]);
      setStaff(staffRows);
      setDepartments(departmentRows.filter((department) => department.is_active));
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load staff.");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // Derived filtered list
  const filteredStaff = useMemo(() => {
    if (!staff) return [];
    const q = search.trim().toLowerCase();
    return staff.filter((s) => {
      if (q) {
        const haystack = [s.name, s.email ?? "", s.phone ?? ""].join(" ").toLowerCase();
        if (!haystack.includes(q)) return false;
      }
      if (filterRole && !s.roles.includes(filterRole)) return false;
      if (filterDepartment && s.department_id !== filterDepartment) return false;
      if (filterStatus === "active" && !s.is_active) return false;
      if (filterStatus === "inactive" && s.is_active) return false;
      return true;
    });
  }, [staff, search, filterRole, filterDepartment, filterStatus]);

  const hasActiveFilters = search || filterRole || filterDepartment || filterStatus;

  function clearFilters() {
    setSearch("");
    setFilterRole("");
    setFilterDepartment("");
    setFilterStatus("");
  }

  async function invite(e: React.FormEvent) {
    e.preventDefault();
    if (!form.name || !form.email) return;
    if (form.role === "VICE_PRINCIPAL" && !form.departmentId) {
      setError("Select the department delegated to this Vice Principal.");
      return;
    }
    setBusy(true);
    try {
      await inviteStaff({
        name: form.name,
        email: form.email,
        phone: form.phone || undefined,
        role: form.role,
        departmentId: form.role === "VICE_PRINCIPAL" ? form.departmentId : undefined,
      });
      setForm({ name: "", email: "", phone: "", role: "TEACHER", departmentId: "" });
      setShowForm(false);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not invite the staff member.");
    } finally {
      setBusy(false);
    }
  }

  function downloadTemplate() {
    const url = URL.createObjectURL(new Blob([TEMPLATE_CSV], { type: "text/csv" }));
    const link = document.createElement("a");
    link.href = url;
    link.download = "staff-template.csv";
    link.click();
    URL.revokeObjectURL(url);
  }

  async function upload() {
    if (!bulkFile) return;
    setBulkBusy(true);
    setBulkError(null);
    setBulkResult(null);
    try {
      const result = await uploadStaff(bulkFile);
      setBulkResult(result);
      if (bulkInputRef.current) bulkInputRef.current.value = "";
      setBulkFile(null);
      await load();
    } catch (err) {
      setBulkError(err instanceof Error ? err.message : "Could not upload the file.");
    } finally {
      setBulkBusy(false);
    }
  }

  async function revokeDepartmentRoleScope(s: StaffMember, roleName: string, departmentId?: string) {
    if (!departmentId) {
      setError(`Select the department to revoke ${roleLabel(roleName as Role)} scope.`);
      return;
    }
    try {
      await revokeStaffRole(s.id, roleName, departmentId);
      setVpDepartments((current) => ({ ...current, [s.id]: "" }));
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : `Could not revoke ${roleLabel(roleName as Role)} delegation.`);
    }
  }

  async function grantRole(s: StaffMember, role: string, departmentId?: string) {
    if ((role === "VICE_PRINCIPAL" || role === "HOD") && !departmentId) {
      setError(`Select a department before assigning the ${roleLabel(role as Role)} role.`);
      return;
    }
    try {
      await assignStaffRole(s.id, role, departmentId);
      if (role === "VICE_PRINCIPAL" || role === "HOD") {
        setVpDepartments((current) => ({ ...current, [s.id]: "" }));
      }
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not assign the role.");
    }
  }

  async function revokeRole(s: StaffMember, roleName: string) {
    try {
      await revokeStaffRole(s.id, roleName);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not revoke the role.");
    }
  }

  function startEdit(s: StaffMember) {
    setEditMember(s);
    setEditForm({
      name: s.name || "",
      email: s.email || "",
      phone: s.phone || "",
      departmentId: s.department_id || "",
    });
  }

  async function saveEdit(e: React.FormEvent) {
    e.preventDefault();
    if (!editMember) return;
    setEditBusy(true);
    try {
      await updateStaff(editMember.id, {
        name: editForm.name,
        email: editForm.email,
        phone: editForm.phone,
        departmentId: editForm.departmentId || undefined,
      });
      setEditMember(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update staff member.");
    } finally {
      setEditBusy(false);
    }
  }

  async function toggleActive(s: StaffMember) {
    try {
      await setStaffActive(s.id, !s.is_active);
      await load();
      if (detailMember && detailMember.id === s.id) {
        setDetailMember({ ...detailMember, is_active: !s.is_active });
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not toggle status.");
    }
  }

  async function handleDelete(s: StaffMember) {
    if (!confirm(`Are you sure you want to delete staff member "${s.name}"? This action cannot be undone.`)) {
      return;
    }
    try {
      await deleteStaff(s.id);
      if (detailMember?.id === s.id) setDetailMember(null);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not delete staff member.");
    }
  }

  async function sendPasswordReset(s: StaffMember) {
    if (!s.email) {
      setError("This staff member has no email address for a password reset link.");
      return;
    }
    setResettingUserId(s.id);
    setError(null);
    try {
      await resendPasswordReset(s.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not send the password reset link.");
    } finally {
      setResettingUserId(null);
    }
  }

  return (
    <div className="mx-auto max-w-4xl">
      <PageHeader
        title="Staff & Users"
        subtitle="Manage institution academic and administrative staff, roles, and profiles."
        action={
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              onClick={() => setShowBulk((v) => !v)}
              className="inline-flex h-10 items-center justify-center gap-2 rounded-field border border-accent-border bg-white px-4 text-sm font-semibold text-accent transition hover:bg-accent-light"
            >
              <Upload className="h-4 w-4" aria-hidden="true" /> Bulk upload
            </button>
            <button
              type="button"
              onClick={() => setShowForm((v) => !v)}
              className="inline-flex h-10 items-center justify-center gap-2 rounded-field bg-accent px-4 text-sm font-semibold text-white shadow-accent transition hover:bg-accent-hover"
            >
              <Plus className="h-4 w-4" aria-hidden="true" /> Invite Staff
            </button>
          </div>
        }
      />

      {showBulk ? (
        <Card className="mb-6">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="min-w-0">
              <p className="text-sm font-bold text-primary">Import staff from CSV</p>
              <p className="mt-1 text-xs text-muted-foreground">
                Headers: <code className="rounded bg-muted px-1 py-0.5">name</code>,{" "}
                <code className="rounded bg-muted px-1 py-0.5">email</code>,{" "}
                <code className="rounded bg-muted px-1 py-0.5">role</code> (required) —{" "}
                <code className="rounded bg-muted px-1 py-0.5">phone</code>,{" "}
                <code className="rounded bg-muted px-1 py-0.5">department_code</code> (optional).
                Use the department <em>code</em> (e.g. CS) to scope the role. Valid roles:{" "}
                <span className="text-primary">{STAFF_INVITABLE_ROLES.map((r) => roleLabel(r)).join(", ")}</span>.
                Vice Principals must have a department code.
              </p>
            </div>
            <button
              type="button"
              onClick={downloadTemplate}
              className="inline-flex h-9 items-center gap-2 rounded border border-border bg-white px-3 text-xs font-semibold text-primary transition hover:bg-muted"
            >
              <Download className="h-3.5 w-3.5" aria-hidden="true" /> Download template
            </button>
          </div>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <input
              ref={bulkInputRef}
              type="file"
              accept=".csv,text/csv"
              onChange={(e) => setBulkFile(e.target.files?.[0] ?? null)}
              className="block w-full max-w-sm text-xs text-muted-foreground file:mr-3 file:rounded file:border-0 file:bg-accent-light file:px-3 file:py-2 file:text-xs file:font-semibold file:text-accent"
            />
            <button
              type="button"
              disabled={bulkBusy || !bulkFile}
              onClick={upload}
              className="inline-flex h-10 items-center justify-center gap-2 rounded-field bg-accent px-4 text-sm font-semibold text-white shadow-accent transition hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-60"
            >
              <Upload className="h-4 w-4" aria-hidden="true" /> {bulkBusy ? "Importing…" : "Import"}
            </button>
          </div>
          <p className="mt-3 text-xs text-muted-foreground">
            Each imported member receives a default password (<code className="rounded bg-muted px-1 py-0.5 font-bold text-primary">password1234!</code>) and an invite email with a set-password link.
          </p>

          {bulkError ? <div className="mt-4"><ErrorState message={bulkError} /></div> : null}

          {bulkResult ? (
            <div className="mt-4 space-y-3">
              <div className="rounded-field border border-border bg-muted/50 p-3 text-sm">
                <span className="font-bold text-primary">{bulkResult.created} of {bulkResult.total} staff imported</span>
                {bulkResult.errors.length ? <span className="text-destructive-text"> · {bulkResult.errors.length} row{bulkResult.errors.length === 1 ? "" : "s"} failed</span> : null}
                {bulkResult.warnings.length ? <span className="text-amber-600"> · {bulkResult.warnings.length} warning{bulkResult.warnings.length === 1 ? "" : "s"}</span> : null}
                {bulkResult.created === bulkResult.total ? <span className="ml-2 text-emerald-600">✓</span> : null}
              </div>
              {bulkResult.errors.length ? (
                <div className="rounded-field border border-destructive-border bg-destructive-light/40 p-3">
                  <p className="mb-1.5 text-xs font-bold uppercase tracking-wide text-destructive-text">Rows that were not imported</p>
                  <ul className="max-h-44 space-y-1 overflow-y-auto text-xs text-primary">
                    {bulkResult.errors.map((issue: BulkUploadRowIssue) => (
                      <li key={`e-${issue.row}`}>Row {issue.row}: <span className="text-destructive-text">{issue.message}</span></li>
                    ))}
                  </ul>
                </div>
              ) : null}
              {bulkResult.warnings.length ? (
                <div className="rounded-field border border-amber-300 bg-amber-50 p-3">
                  <p className="mb-1.5 text-xs font-bold uppercase tracking-wide text-amber-700">Imported, but not scoped to a department</p>
                  <ul className="max-h-44 space-y-1 overflow-y-auto text-xs text-primary">
                    {bulkResult.warnings.map((issue: BulkUploadRowIssue) => (
                      <li key={`w-${issue.row}`}>Row {issue.row}: {issue.message}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>
          ) : null}
        </Card>
      ) : null}

      {showForm ? (
        <Card className="mb-6">
          <form onSubmit={invite} className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className={labelClass}>Full name</label>
              <input className={inputClass} value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Priya Nair" required />
            </div>
            <div>
              <label className={labelClass}>Email</label>
              <input type="email" className={inputClass} value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="priya@college.edu" required />
            </div>
            <div>
              <label className={labelClass}>Phone (optional)</label>
              <input className={inputClass} value={form.phone} onChange={(e) => setForm({ ...form, phone: e.target.value })} placeholder="+91 …" />
            </div>
            <div>
              <label className={labelClass}>Role</label>
              <select className={inputClass} value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value, departmentId: "" })}>
                {STAFF_INVITABLE_ROLES.map((r) => (
                  <option key={r} value={r}>{roleLabel(r)}</option>
                ))}
              </select>
            </div>
            {form.role === "VICE_PRINCIPAL" || form.role === "HOD" ? (
              <div className="sm:col-span-2">
                <label className={labelClass}>
                  {form.role === "HOD" ? "Department to head (HOD)" : "Delegated department"}
                </label>
                <select
                  className={inputClass}
                  value={form.departmentId}
                  onChange={(event) => setForm({ ...form, departmentId: event.target.value })}
                  required
                >
                  <option value="">Select a department</option>
                  {departments.map((department) => (
                    <option key={department.id} value={department.id}>{department.name}</option>
                  ))}
                </select>
                <p className="mt-1 text-xs text-muted-foreground">
                  {form.role === "HOD"
                    ? "Assigning an HOD creates their department-scoped HOD role for this department."
                    : "Vice Principals can view and post only within their delegated department and its classes."}
                </p>
              </div>
            ) : null}
            <div className="sm:col-span-2 flex flex-wrap items-center justify-between gap-3">
              <button type="submit" disabled={busy} className="inline-flex h-11 items-center justify-center gap-2 rounded-field bg-accent px-5 text-sm font-semibold text-white shadow-accent transition hover:bg-accent-hover disabled:opacity-60">
                <UserPlus className="h-4 w-4" aria-hidden="true" /> {busy ? "Inviting…" : "Send invite"}
              </button>
              <p className="text-xs text-muted-foreground">
                Default password: <code className="rounded bg-muted px-1.5 py-0.5 font-bold text-primary">password1234!</code>
              </p>
            </div>
          </form>
        </Card>
      ) : null}

      {error ? <div className="mb-4"><ErrorState message={error} /></div> : null}

      {/* Search & Filter Bar */}
      {staff !== null && staff.length > 0 ? (
        <Card className="mb-4 !p-4">
          <div className="flex flex-wrap items-center gap-3">
            {/* Search input */}
            <div className="relative min-w-0 flex-1" style={{ minWidth: "180px" }}>
              <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" aria-hidden="true" />
              <input
                type="search"
                placeholder="Search by name, email or phone…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="h-10 w-full rounded-field border border-[#E2E8F0] bg-white pl-9 pr-3.5 text-sm text-primary outline-none transition placeholder:text-[#94A3B8] focus:border-accent focus:ring-3 focus:ring-accent/15"
                aria-label="Search staff"
              />
            </div>

            {/* Filter divider */}
            <span className="hidden items-center gap-1.5 text-xs font-medium text-muted-foreground sm:flex">
              <SlidersHorizontal className="h-3.5 w-3.5" aria-hidden="true" /> Filters
            </span>

            {/* Role filter */}
            <select
              value={filterRole}
              onChange={(e) => setFilterRole(e.target.value)}
              className="h-10 rounded-field border border-[#E2E8F0] bg-white px-3 text-sm text-primary outline-none transition focus:border-accent focus:ring-3 focus:ring-accent/15"
              aria-label="Filter by role"
            >
              <option value="">All roles</option>
              {STAFF_INVITABLE_ROLES.map((r) => (
                <option key={r} value={r}>{roleLabel(r)}</option>
              ))}
            </select>

            {/* Department filter */}
            {departments.length > 0 ? (
              <select
                value={filterDepartment}
                onChange={(e) => setFilterDepartment(e.target.value)}
                className="h-10 rounded-field border border-[#E2E8F0] bg-white px-3 text-sm text-primary outline-none transition focus:border-accent focus:ring-3 focus:ring-accent/15"
                aria-label="Filter by department"
              >
                <option value="">All departments</option>
                {departments.map((d) => (
                  <option key={d.id} value={d.id}>{d.name}</option>
                ))}
              </select>
            ) : null}

            {/* Status filter */}
            <select
              value={filterStatus}
              onChange={(e) => setFilterStatus(e.target.value as "" | "active" | "inactive")}
              className="h-10 rounded-field border border-[#E2E8F0] bg-white px-3 text-sm text-primary outline-none transition focus:border-accent focus:ring-3 focus:ring-accent/15"
              aria-label="Filter by status"
            >
              <option value="">All statuses</option>
              <option value="active">Active</option>
              <option value="inactive">Inactive</option>
            </select>

            {/* Clear filters */}
            {hasActiveFilters ? (
              <button
                type="button"
                onClick={clearFilters}
                className="inline-flex h-10 items-center gap-1.5 rounded-field border border-border bg-white px-3 text-xs font-semibold text-muted-foreground transition hover:border-destructive-border hover:text-destructive-text"
              >
                <X className="h-3.5 w-3.5" /> Clear
              </button>
            ) : null}
          </div>

          {/* Result count */}
          <p className="mt-2.5 text-xs text-muted-foreground">
            {hasActiveFilters
              ? `${filteredStaff.length} of ${staff.length} staff member${staff.length === 1 ? "" : "s"} match`
              : `${staff.length} staff member${staff.length === 1 ? "" : "s"} total`}
          </p>
        </Card>
      ) : null}

      {staff === null ? (
        <Loading />
      ) : staff.length === 0 ? (
        <EmptyState text="No staff yet. Invite your first team member." />
      ) : filteredStaff.length === 0 ? (
        <EmptyState text="No staff members match your search or filters." />
      ) : (
        <ul className="space-y-4">
          {filteredStaff.map((s) => (
            <li key={s.id}>
              <Card className="!p-5">
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <p className="font-display text-base font-bold text-primary">{s.name}</p>
                      <span className={`inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-[11px] font-bold ${s.is_active ? "bg-emerald-50 text-emerald-700 border border-emerald-200" : "bg-destructive-light text-destructive-text border border-destructive-border"}`}>
                        {s.is_active ? <CheckCircle2 className="h-3 w-3" /> : <XCircle className="h-3 w-3" />}
                        {s.is_active ? "Active" : "Inactive"}
                      </span>
                    </div>
                    <div className="mt-1 flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-muted-foreground">
                      <span className="flex items-center gap-1">
                        <Mail className="h-3.5 w-3.5" />
                        {s.email ?? "No email"}
                      </span>
                      {s.phone ? (
                        <span className="flex items-center gap-1">
                          <Phone className="h-3.5 w-3.5" />
                          {s.phone}
                        </span>
                      ) : null}
                      {s.department_name ? (
                        <span className="flex items-center gap-1 font-semibold text-primary">
                          <Building2 className="h-3.5 w-3.5 text-accent" />
                          {s.department_name}
                        </span>
                      ) : null}
                    </div>
                  </div>

                  {/* Actions Toolbar */}
                  <div className="flex flex-wrap items-center gap-1.5">
                    <button
                      type="button"
                      onClick={() => setDetailMember(s)}
                      className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-white px-2.5 text-xs font-semibold text-primary transition hover:bg-muted"
                      title="View Details"
                    >
                      <Eye className="h-3.5 w-3.5" /> Details
                    </button>

                    <button
                      type="button"
                      onClick={() => startEdit(s)}
                      className="inline-flex h-8 items-center gap-1.5 rounded-md border border-border bg-white px-2.5 text-xs font-semibold text-accent transition hover:bg-accent-light hover:border-accent-border"
                      title="Edit Staff Member"
                    >
                      <Edit className="h-3.5 w-3.5" /> Edit
                    </button>

                    <button
                      type="button"
                      disabled={!s.is_active || !s.email || resettingUserId === s.id}
                      onClick={() => sendPasswordReset(s)}
                      className="inline-flex h-8 items-center gap-1.5 rounded-md border border-accent-border bg-white px-2.5 text-xs font-semibold text-accent transition hover:bg-accent-light disabled:cursor-not-allowed disabled:opacity-50"
                      title={s.email ? "Send password reset link" : "No email address"}
                    >
                      <Mail className="h-3.5 w-3.5" /> {resettingUserId === s.id ? "Sending..." : "Reset link"}
                    </button>

                    <button
                      type="button"
                      onClick={() => toggleActive(s)}
                      className={`inline-flex h-8 items-center gap-1.5 rounded-md border px-2.5 text-xs font-semibold transition ${
                        s.is_active
                          ? "border-amber-200 bg-amber-50 text-amber-700 hover:bg-amber-100"
                          : "border-emerald-200 bg-emerald-50 text-emerald-700 hover:bg-emerald-100"
                      }`}
                      title={s.is_active ? "Deactivate Staff Member" : "Activate Staff Member"}
                    >
                      <Power className="h-3.5 w-3.5" /> {s.is_active ? "Deactivate" : "Activate"}
                    </button>

                    <button
                      type="button"
                      onClick={() => handleDelete(s)}
                      className="inline-flex h-8 items-center gap-1 rounded-md border border-destructive-border bg-white px-2 text-xs font-semibold text-destructive-text transition hover:bg-destructive-light"
                      title="Delete Staff Member"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>

                {/* Role Badges with Direct Revocation */}
                <div className="mt-3 flex flex-wrap items-center gap-1.5">
                  <span className="text-xs font-medium text-muted-foreground mr-1">Assigned Roles:</span>
                  {s.roles.length === 0 ? (
                    <span className="text-xs italic text-muted-foreground">No active roles</span>
                  ) : (
                    s.roles.map((r) => (
                      <span key={r} className="inline-flex items-center gap-1 rounded-full bg-accent-light px-2.5 py-0.5 text-[11px] font-semibold text-accent border border-accent-border/40">
                        {roleLabel(r as Role)}
                        {s.roles.length > 1 ? (
                          <button
                            type="button"
                            onClick={() => revokeRole(s, r)}
                            className="rounded-full p-0.5 text-accent hover:bg-accent/20 transition"
                            title={`Revoke ${roleLabel(r as Role)} role`}
                          >
                            <X className="h-3 w-3" />
                          </button>
                        ) : null}
                      </span>
                    ))
                  )}
                </div>

                {/* Add Role Dropdown */}
                <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-border pt-3">
                  <span className="text-xs font-medium text-muted-foreground">Add role:</span>
                  {STAFF_INVITABLE_ROLES.filter((r) => r !== "VICE_PRINCIPAL" && r !== "HOD" && !s.roles.includes(r)).slice(0, 5).map((r) => (
                    <button key={r} type="button" onClick={() => grantRole(s, r)} className="rounded-full border border-border px-2.5 py-1 text-[11px] font-medium text-[#475569] transition hover:border-accent hover:text-accent">
                      + {roleLabel(r).toLowerCase()}
                    </button>
                  ))}
                </div>

                {/* Department Role Delegation (VP / HOD) */}
                {departments.length ? (
                  <div className="mt-3 flex flex-wrap items-center gap-2 rounded-field bg-muted p-2.5">
                    <label htmlFor={`dept-scope-${s.id}`} className="text-xs font-semibold text-primary">
                      Department Scope Assignment
                    </label>
                    <select
                      id={`dept-scope-${s.id}`}
                      className="h-8 min-w-44 rounded border border-border bg-white px-2 text-xs text-primary"
                      value={vpDepartments[s.id] ?? ""}
                      onChange={(event) => setVpDepartments({ ...vpDepartments, [s.id]: event.target.value })}
                    >
                      <option value="">Select department</option>
                      {departments.map((department) => (
                        <option key={department.id} value={department.id}>{department.name}</option>
                      ))}
                    </select>
                    <button
                      type="button"
                      disabled={!vpDepartments[s.id]}
                      onClick={() => grantRole(s, "HOD", vpDepartments[s.id])}
                      className="h-8 rounded border border-accent-border bg-white px-2.5 text-xs font-semibold text-accent transition hover:bg-accent-light disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      Assign HOD
                    </button>
                    <button
                      type="button"
                      disabled={!vpDepartments[s.id]}
                      onClick={() => grantRole(s, "VICE_PRINCIPAL", vpDepartments[s.id])}
                      className="h-8 rounded border border-accent-border bg-white px-2.5 text-xs font-semibold text-accent transition hover:bg-accent-light disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      Assign VP
                    </button>
                    {s.roles.includes("HOD") ? (
                      <button
                        type="button"
                        disabled={!vpDepartments[s.id]}
                        onClick={() => revokeDepartmentRoleScope(s, "HOD", vpDepartments[s.id])}
                        className="h-8 rounded border border-destructive-border bg-white px-2.5 text-xs font-semibold text-destructive-text transition hover:bg-destructive-light disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        Revoke HOD
                      </button>
                    ) : null}
                    {s.roles.includes("VICE_PRINCIPAL") ? (
                      <button
                        type="button"
                        disabled={!vpDepartments[s.id]}
                        onClick={() => revokeDepartmentRoleScope(s, "VICE_PRINCIPAL", vpDepartments[s.id])}
                        className="h-8 rounded border border-destructive-border bg-white px-2.5 text-xs font-semibold text-destructive-text transition hover:bg-destructive-light disabled:cursor-not-allowed disabled:opacity-50"
                      >
                        Revoke VP
                      </button>
                    ) : null}
                  </div>
                ) : null}
              </Card>
            </li>
          ))}
        </ul>
      )}

      {/* Edit Staff Modal */}
      {editMember ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm">
          <div className="w-full max-w-lg rounded-xl border border-border bg-white p-6 shadow-2xl animate-in fade-in zoom-in duration-150">
            <div className="flex items-center justify-between border-b border-border pb-4">
              <div>
                <h2 className="font-display text-lg font-bold text-primary">Edit Staff Details</h2>
                <p className="text-xs text-muted-foreground">Update contact information and department assignment.</p>
              </div>
              <button
                type="button"
                onClick={() => setEditMember(null)}
                className="rounded-lg p-1.5 text-muted-foreground transition hover:bg-muted hover:text-primary"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <form onSubmit={saveEdit} className="mt-4 space-y-4">
              <div>
                <label className={labelClass}>Full Name</label>
                <input
                  type="text"
                  className={inputClass}
                  value={editForm.name}
                  onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                  required
                />
              </div>

              <div>
                <label className={labelClass}>Email Address</label>
                <input
                  type="email"
                  className={inputClass}
                  value={editForm.email}
                  onChange={(e) => setEditForm({ ...editForm, email: e.target.value })}
                  required
                />
              </div>

              <div>
                <label className={labelClass}>Phone Number</label>
                <input
                  type="text"
                  className={inputClass}
                  value={editForm.phone}
                  onChange={(e) => setEditForm({ ...editForm, phone: e.target.value })}
                  placeholder="+91 …"
                />
              </div>

              <div>
                <label className={labelClass}>Department</label>
                <select
                  className={inputClass}
                  value={editForm.departmentId}
                  onChange={(e) => setEditForm({ ...editForm, departmentId: e.target.value })}
                >
                  <option value="">Unassigned / General</option>
                  {departments.map((dept) => (
                    <option key={dept.id} value={dept.id}>
                      {dept.name} ({dept.code})
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex items-center justify-end gap-3 pt-4 border-t border-border">
                <button
                  type="button"
                  onClick={() => setEditMember(null)}
                  className="rounded-field border border-border px-4 py-2 text-xs font-semibold text-primary transition hover:bg-muted"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={editBusy}
                  className="rounded-field bg-accent px-5 py-2 text-xs font-semibold text-white shadow-accent transition hover:bg-accent-hover disabled:opacity-60"
                >
                  {editBusy ? "Saving..." : "Save Changes"}
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : null}

      {/* Staff Details Modal */}
      {detailMember ? (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm">
          <div className="w-full max-w-lg rounded-xl border border-border bg-white p-6 shadow-2xl animate-in fade-in zoom-in duration-150">
            <div className="flex items-center justify-between border-b border-border pb-4">
              <div className="flex items-center gap-3">
                <div className="flex h-12 w-12 items-center justify-center rounded-full bg-accent-light text-accent font-display text-lg font-bold">
                  {detailMember.name.slice(0, 2).toUpperCase()}
                </div>
                <div>
                  <h2 className="font-display text-lg font-bold text-primary">{detailMember.name}</h2>
                  <span className={`inline-flex items-center gap-1 text-xs font-semibold ${detailMember.is_active ? "text-emerald-600" : "text-destructive-text"}`}>
                    {detailMember.is_active ? "● Active Staff Member" : "○ Inactive"}
                  </span>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setDetailMember(null)}
                className="rounded-lg p-1.5 text-muted-foreground transition hover:bg-muted hover:text-primary"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="mt-4 space-y-4 text-xs">
              <div className="grid grid-cols-2 gap-4 rounded-field bg-muted/60 p-4">
                <div>
                  <p className="text-muted-foreground">Email</p>
                  <p className="font-semibold text-primary mt-0.5">{detailMember.email ?? "—"}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Phone</p>
                  <p className="font-semibold text-primary mt-0.5">{detailMember.phone ?? "—"}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Department</p>
                  <p className="font-semibold text-primary mt-0.5">{detailMember.department_name ?? "Unassigned"}</p>
                </div>
                <div>
                  <p className="text-muted-foreground">Last Login</p>
                  <p className="font-semibold text-primary mt-0.5">
                    {detailMember.last_login_at ? new Date(detailMember.last_login_at).toLocaleDateString() : "Never"}
                  </p>
                </div>
              </div>

              <div>
                <p className="font-bold text-primary mb-2">Assigned Roles</p>
                <div className="flex flex-wrap gap-1.5">
                  {detailMember.roles.map((role) => (
                    <span key={role} className="rounded-full bg-accent-light px-3 py-1 text-xs font-semibold text-accent border border-accent-border/50">
                      {roleLabel(role as Role)}
                    </span>
                  ))}
                </div>
              </div>

              <div className="flex items-center justify-between pt-4 border-t border-border">
                <div className="flex items-center gap-2">
                  <button
                    type="button"
                    onClick={() => {
                      const m = detailMember;
                      setDetailMember(null);
                      startEdit(m);
                    }}
                    className="inline-flex items-center gap-1.5 rounded-field border border-accent-border bg-accent-light px-3 py-1.5 text-xs font-semibold text-accent transition hover:bg-accent hover:text-white"
                  >
                    <Edit className="h-3.5 w-3.5" /> Edit Profile
                  </button>
                  <button
                    type="button"
                    onClick={() => toggleActive(detailMember)}
                    className="inline-flex items-center gap-1.5 rounded-field border border-border bg-white px-3 py-1.5 text-xs font-semibold text-primary transition hover:bg-muted"
                  >
                    <Power className="h-3.5 w-3.5" /> {detailMember.is_active ? "Deactivate" : "Activate"}
                  </button>
                </div>
                <button
                  type="button"
                  onClick={() => setDetailMember(null)}
                  className="rounded-field border border-border px-4 py-1.5 text-xs font-semibold text-primary transition hover:bg-muted"
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        </div>
      ) : null}
    </div>
  );
}

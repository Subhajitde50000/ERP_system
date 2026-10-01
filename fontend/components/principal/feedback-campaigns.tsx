"use client";

import { useCallback, useEffect, useState } from "react";

import { Card, EmptyState, Loading, PageHeader, inputClass, labelClass } from "@/components/admin/ui";
import { dateTime, statusLabel } from "@/components/principal/principal-ui";
import {
  BarChart3,
  CheckCircle2,
  ChevronRight,
  Loader2,
  Maximize2,
  MessageSquareMore,
  Minimize2,
  Plus,
  Trash2,
  X,
} from "lucide-react";

import {
  type CampaignCreate,
  type CampaignDetail,
  type CampaignRow,
  type CampaignAnalytics,
  type CampaignTargetIn,
  closeCampaign,
  createCampaign,
  deleteCampaign,
  getCampaign,
  getCampaignAnalytics,
  listCampaigns,
  publishCampaign,
} from "@/lib/feedback";
import { fetchStaff } from "@/lib/institution";
import { fetchPrincipalStaff, type PrincipalStaffRow } from "@/lib/principal";

type AdminPrefix = "feedback" | "principal/feedback";

const STATUS_CLASS: Record<string, string> = {
  DRAFT: "bg-warning-light text-warning-text",
  ACTIVE: "bg-success-light text-success-text",
  CLOSED: "bg-muted text-muted-foreground",
};

function RatingBar({ label, value }: { label: string; value: number | null }) {
  if (value === null) return null;
  const pct = Math.round((value / 5) * 100);
  return (
    <div className="flex items-center gap-3">
      <span className="w-40 text-sm text-muted-foreground">{label}</span>
      <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
        <div className="h-full rounded-full bg-accent" style={{ width: `${pct}%` }} />
      </div>
      <span className="text-sm font-semibold w-12 text-right">{value.toFixed(1)}/5</span>
    </div>
  );
}

interface Props {
  apiPrefix: AdminPrefix;
}

export function FeedbackCampaignsPage({ apiPrefix }: Props) {
  const [campaigns, setCampaigns] = useState<CampaignRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Detail / analytics panel state
  const [detailId, setDetailId] = useState<string | null>(null);
  const [detail, setDetail] = useState<CampaignDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [analytics, setAnalytics] = useState<CampaignAnalytics | null>(null);
  const [analyticsLoading, setAnalyticsLoading] = useState(false);
  const [isFullScreen, setIsFullScreen] = useState(false);

  // Create modal state
  const [showCreate, setShowCreate] = useState(false);
  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState<string | null>(null);
  const [allTeachers, setAllTeachers] = useState(false);
  const [form, setForm] = useState<Omit<CampaignCreate, "targets">>({
    title: "",
    description: null,
    starts_at: "",
    ends_at: "",
    allow_anonymous: true,
  });
  const [targetRows, setTargetRows] = useState<CampaignTargetIn[]>([
    { teacher_id: "", subject_id: null, class_id: null },
  ]);
  const [staffList, setStaffList] = useState<Pick<PrincipalStaffRow, "id" | "name">[]>([]);

  const loadCampaigns = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await listCampaigns(apiPrefix);
      setCampaigns(res.items);
    } catch {
      setError("Failed to load feedback campaigns.");
    } finally {
      setLoading(false);
    }
  }, [apiPrefix]);

  useEffect(() => { loadCampaigns(); }, [loadCampaigns]);

  useEffect(() => {
    if (apiPrefix === "feedback") {
      fetchStaff()
        .then((members) => {
          if (Array.isArray(members)) {
            setStaffList(members.map((s) => ({ id: s.id, name: s.name })));
          }
        })
        .catch(() => {});
    } else {
      fetchPrincipalStaff({ limit: 200 })
        .then((r) => {
          if (r?.items) setStaffList(r.items);
        })
        .catch(() => {
          fetchStaff()
            .then((members) => {
              if (Array.isArray(members)) {
                setStaffList(members.map((s) => ({ id: s.id, name: s.name })));
              }
            })
            .catch(() => {});
        });
    }
  }, [apiPrefix]);

  const openDetail = async (id: string) => {
    setDetailId(id);
    setDetail(null);
    setAnalytics(null);
    setIsFullScreen(false);
    setDetailLoading(true);
    try {
      const res = await getCampaign(apiPrefix, id);
      setDetail(res);
    } catch {
      setDetailId(null);
    } finally {
      setDetailLoading(false);
    }
  };

  const loadAnalytics = async (id: string) => {
    setAnalyticsLoading(true);
    try {
      const res = await getCampaignAnalytics(apiPrefix, id);
      setAnalytics(res);
    } catch {
      // analytics load failure is non-fatal
    } finally {
      setAnalyticsLoading(false);
    }
  };

  const handleCreate = async () => {
    const validTargets = allTeachers
      ? staffList.map((s) => ({ teacher_id: s.id, subject_id: null, class_id: null }))
      : targetRows.filter((t) => t.teacher_id.trim() && t.teacher_id !== "ALL");

    if (!form.title.trim()) { setCreateError("Campaign title is required."); return; }
    if (!form.starts_at || !form.ends_at) { setCreateError("Start and end dates are required."); return; }
    if (!validTargets.length) {
      setCreateError(allTeachers ? "No teachers found in the system to target." : "Add at least one teacher target.");
      return;
    }
    setCreating(true);
    setCreateError(null);
    try {
      await createCampaign(apiPrefix, { ...form, targets: validTargets });
      setShowCreate(false);
      setAllTeachers(false);
      setForm({ title: "", description: null, starts_at: "", ends_at: "", allow_anonymous: true });
      setTargetRows([{ teacher_id: "", subject_id: null, class_id: null }]);
      loadCampaigns();
    } catch (e: unknown) {
      setCreateError(e instanceof Error ? e.message : "Failed to create campaign.");
    } finally {
      setCreating(false);
    }
  };

  const handlePublish = async (id: string) => {
    try {
      await publishCampaign(apiPrefix, id);
      setDetailId(null);
      setDetail(null);
      loadCampaigns();
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "Publish failed.");
    }
  };

  const handleClose = async (id: string) => {
    try {
      await closeCampaign(apiPrefix, id);
      setDetailId(null);
      setDetail(null);
      loadCampaigns();
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "Close failed.");
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Delete this draft campaign? This cannot be undone.")) return;
    try {
      await deleteCampaign(apiPrefix, id);
      setDetailId(null);
      loadCampaigns();
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : "Delete failed.");
    }
  };

  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader
        title="Feedback Campaigns"
        subtitle="Manage teacher feedback campaigns. Students rate only the teachers they study under."
        action={
          <button
            type="button"
            onClick={() => setShowCreate(true)}
            className="inline-flex h-10 items-center gap-2 rounded-field bg-accent px-4 text-sm font-semibold text-white shadow-accent transition hover:bg-accent-hover"
          >
            <Plus className="h-4 w-4" /> New Campaign
          </button>
        }
      />

      {loading ? (
        <Loading label="Loading campaigns…" />
      ) : error ? (
        <div role="alert" className="rounded-card border border-destructive-border bg-destructive-light px-5 py-10 text-center text-sm font-medium text-destructive-text">
          {error}
        </div>
      ) : campaigns.length === 0 ? (
        <EmptyState text="No feedback campaigns yet. Create your first campaign to collect teacher feedback from students." />
      ) : (
        <div className="space-y-3">
          {campaigns.map((c) => (
            <Card key={c.id}>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="min-w-0 flex-1">
                  <div className="mb-1.5 flex flex-wrap items-center gap-2">
                    <span className={`rounded-full px-2.5 py-1 text-[11px] font-bold ${STATUS_CLASS[c.status] ?? "bg-muted text-muted-foreground"}`}>
                      {statusLabel(c.status)}
                    </span>
                    <span className="rounded-full bg-muted px-2.5 py-1 text-[11px] font-bold text-muted-foreground">
                      {c.target_count} teacher{c.target_count !== 1 ? "s" : ""}
                    </span>
                    {c.allow_anonymous && (
                      <span className="rounded-full bg-muted px-2.5 py-1 text-[11px] font-bold text-muted-foreground">
                        Anonymous
                      </span>
                    )}
                  </div>
                  <h2 className="font-display text-base font-bold text-primary">{c.title}</h2>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {dateTime(c.starts_at)} → {dateTime(c.ends_at)}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => openDetail(c.id)}
                  className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-field border border-border px-3 text-xs font-semibold text-foreground transition hover:border-accent hover:text-accent"
                >
                  <ChevronRight className="h-3.5 w-3.5" /> View
                </button>
              </div>
            </Card>
          ))}
        </div>
      )}

      {/* Detail modal */}
      {detailId && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label="Campaign details"
          className={`fixed inset-0 z-50 flex ${
            isFullScreen ? "p-0 bg-white" : "items-center justify-center bg-primary/50 p-4"
          }`}
        >
          <div
            className={`overflow-y-auto bg-white transition-all ${
              isFullScreen
                ? "h-full w-full rounded-none p-6 sm:p-8"
                : "max-h-[90vh] w-full max-w-2xl rounded-card p-5 shadow-2xl sm:p-6"
            }`}
          >
            <div className={isFullScreen ? "mx-auto max-w-5xl" : ""}>
              <div className="mb-5 flex items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                  <h2 className="font-display text-lg font-bold text-primary">Campaign Details</h2>
                  {isFullScreen && (
                    <span className="rounded-full bg-muted px-2.5 py-0.5 text-xs font-semibold text-muted-foreground">
                      Full Screen
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-1">
                  <button
                    type="button"
                    onClick={() => setIsFullScreen(!isFullScreen)}
                    aria-label={isFullScreen ? "Exit full screen" : "Open full screen"}
                    title={isFullScreen ? "Exit full screen" : "Open full screen"}
                    className="rounded-lg p-2 text-muted-foreground hover:bg-muted hover:text-primary transition"
                  >
                    {isFullScreen ? (
                      <Minimize2 className="h-4 w-4" />
                    ) : (
                      <Maximize2 className="h-4 w-4" />
                    )}
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setDetailId(null);
                      setDetail(null);
                      setAnalytics(null);
                      setIsFullScreen(false);
                    }}
                    aria-label="Close"
                    title="Close"
                    className="rounded-lg p-2 text-muted-foreground hover:bg-muted hover:text-primary transition"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
              </div>

              {detailLoading ? (
                <Loading label="Loading…" />
              ) : detail ? (
                <div className="space-y-5">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className={`rounded-full px-2.5 py-1 text-[11px] font-bold ${STATUS_CLASS[detail.status] ?? ""}`}>
                      {statusLabel(detail.status)}
                    </span>
                    {detail.allow_anonymous && (
                      <span className="rounded-full bg-muted px-2.5 py-1 text-[11px] font-bold text-muted-foreground">Anonymous</span>
                    )}
                  </div>
                  <h3 className="font-display text-xl font-bold text-primary">{detail.title}</h3>
                  {detail.description && <p className="text-sm text-muted-foreground">{detail.description}</p>}

                  <div className="grid grid-cols-2 gap-4 border-t border-border pt-4 text-sm">
                    <div>
                      <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Opens</p>
                      <p className="mt-1 font-medium text-primary">{dateTime(detail.starts_at)}</p>
                    </div>
                    <div>
                      <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">Closes</p>
                      <p className="mt-1 font-medium text-primary">{dateTime(detail.ends_at)}</p>
                    </div>
                  </div>

                  <div className="border-t border-border pt-4">
                    <p className="mb-2 font-display text-sm font-bold text-primary">Teacher Targets ({detail.targets.length})</p>
                    <ul className={`space-y-1 ${isFullScreen ? "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2 space-y-0" : ""}`}>
                      {detail.targets.map((t) => (
                        <li key={t.id} className="flex items-center gap-2 text-sm text-muted-foreground">
                          <ChevronRight className="h-3.5 w-3.5 shrink-0" />
                          <span className="font-medium text-primary">{t.teacher_name ?? t.teacher_id}</span>
                          {t.subject_name && <span>— {t.subject_name}</span>}
                          {t.class_name && <span className="text-xs">({t.class_name})</span>}
                        </li>
                      ))}
                    </ul>
                  </div>

                  {/* Analytics */}
                  {detail.status !== "DRAFT" && (
                    <div className="border-t border-border pt-4">
                      <div className="mb-3 flex items-center justify-between">
                        <p className="font-display text-sm font-bold text-primary">Analytics</p>
                        {!analytics && !analyticsLoading && (
                          <button
                            type="button"
                            onClick={() => loadAnalytics(detail.id)}
                            className="inline-flex h-8 items-center gap-1.5 rounded-field border border-border px-3 text-xs font-semibold text-foreground transition hover:border-accent hover:text-accent"
                          >
                            <BarChart3 className="h-3.5 w-3.5" /> Load Analytics
                          </button>
                        )}
                        {analyticsLoading && <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />}
                      </div>
                      {analytics && (
                        <div className="space-y-4">
                          <p className="text-sm text-muted-foreground">
                            Total responses: <span className="font-semibold text-primary">{analytics.total_responses}</span>
                          </p>
                          <div className={isFullScreen ? "grid grid-cols-1 md:grid-cols-2 gap-4 space-y-0" : "space-y-4"}>
                            {analytics.results.map((r) => (
                              <div key={r.teacher_id} className="rounded-field border border-border p-4">
                                <p className="font-display text-sm font-bold text-primary">{r.teacher_name ?? r.teacher_id}</p>
                                <p className="mb-3 text-xs text-muted-foreground">{r.response_count} response{r.response_count !== 1 ? "s" : ""}</p>
                                <div className="space-y-2">
                                  <RatingBar label="Teaching Clarity" value={r.teaching_clarity_avg} />
                                  <RatingBar label="Subject Knowledge" value={r.subject_knowledge_avg} />
                                  <RatingBar label="Interaction" value={r.interaction_avg} />
                                  <RatingBar label="Overall" value={r.overall_avg} />
                                </div>
                                {r.comments && r.comments.length > 0 && (
                                  <div className="mt-3">
                                    <p className="mb-1.5 text-xs font-semibold text-muted-foreground">Comments</p>
                                    <ul className="space-y-1">
                                      {r.comments.map((comment, i) => (
                                        <li key={i} className="rounded-field bg-muted px-3 py-2 text-xs">"{comment}"</li>
                                      ))}
                                    </ul>
                                  </div>
                                )}
                              </div>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Actions */}
                  <div className="flex flex-wrap gap-3 border-t border-border pt-4">
                    {detail.status === "DRAFT" && (
                      <>
                        <button
                          type="button"
                          onClick={() => handleDelete(detail.id)}
                          className="inline-flex h-10 items-center gap-2 rounded-field border border-destructive-border bg-destructive-light px-4 text-sm font-semibold text-destructive-text transition hover:opacity-80"
                        >
                          <Trash2 className="h-4 w-4" /> Delete
                        </button>
                        <button
                          type="button"
                          onClick={() => handlePublish(detail.id)}
                          className="inline-flex h-10 items-center gap-2 rounded-field bg-accent px-4 text-sm font-semibold text-white shadow-accent transition hover:bg-accent-hover"
                        >
                          <CheckCircle2 className="h-4 w-4" /> Publish Campaign
                        </button>
                      </>
                    )}
                    {detail.status === "ACTIVE" && (
                      <button
                        type="button"
                        onClick={() => handleClose(detail.id)}
                        className="inline-flex h-10 items-center gap-2 rounded-field border border-border px-4 text-sm font-semibold text-foreground transition hover:border-accent hover:text-accent"
                      >
                        <X className="h-4 w-4" /> Close Campaign
                      </button>
                    )}
                  </div>
                </div>
              ) : null}
            </div>
          </div>
        </div>
      )}

      {/* Create modal */}
      {showCreate && (
        <div role="dialog" aria-modal="true" aria-label="Create feedback campaign" className="fixed inset-0 z-50 flex items-center justify-center bg-primary/50 p-4">
          <div className="max-h-[90vh] w-full max-w-xl overflow-y-auto rounded-card bg-white p-5 shadow-2xl sm:p-6">
            <div className="mb-5 flex items-center justify-between gap-3">
              <h2 className="font-display text-lg font-bold text-primary">New Feedback Campaign</h2>
              <button type="button" onClick={() => setShowCreate(false)} aria-label="Close" className="rounded-lg p-2 text-muted-foreground hover:bg-muted hover:text-primary">
                <X className="h-4 w-4" />
              </button>
            </div>

            <div className="space-y-4">
              <div>
                <label htmlFor="fc-title" className={labelClass}>Campaign Title *</label>
                <input
                  id="fc-title"
                  className={inputClass}
                  placeholder="e.g. Teacher Feedback — Semester 1"
                  value={form.title}
                  onChange={(e) => setForm({ ...form, title: e.target.value })}
                  maxLength={200}
                />
              </div>

              <div>
                <label htmlFor="fc-desc" className={labelClass}>Description (optional)</label>
                <textarea
                  id="fc-desc"
                  className={`${inputClass} min-h-16 py-2`}
                  rows={2}
                  placeholder="Short note for students"
                  value={form.description ?? ""}
                  onChange={(e) => setForm({ ...form, description: e.target.value || null })}
                />
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <label htmlFor="fc-start" className={labelClass}>Opens At *</label>
                  <input
                    id="fc-start"
                    type="datetime-local"
                    className={inputClass}
                    value={form.starts_at}
                    onChange={(e) => setForm({ ...form, starts_at: e.target.value })}
                  />
                </div>
                <div>
                  <label htmlFor="fc-end" className={labelClass}>Closes At *</label>
                  <input
                    id="fc-end"
                    type="datetime-local"
                    className={inputClass}
                    value={form.ends_at}
                    onChange={(e) => setForm({ ...form, ends_at: e.target.value })}
                  />
                </div>
              </div>

              <label className="flex cursor-pointer items-center gap-2.5 text-sm font-medium text-primary">
                <input
                  type="checkbox"
                  checked={form.allow_anonymous}
                  onChange={(e) => setForm({ ...form, allow_anonymous: e.target.checked })}
                  className="h-4 w-4 rounded border-border accent-accent"
                />
                Anonymous feedback
                <span className="text-xs font-normal text-muted-foreground">(students hidden from teachers)</span>
              </label>

              <div className="border-t border-border pt-4">
                <div className="mb-2 flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <label className={labelClass}>Teacher Targets *</label>
                    <label className="flex cursor-pointer items-center gap-1.5 text-xs font-semibold text-accent">
                      <input
                        type="checkbox"
                        checked={allTeachers}
                        onChange={(e) => {
                          setAllTeachers(e.target.checked);
                          if (!e.target.checked && targetRows.length === 0) {
                            setTargetRows([{ teacher_id: "", subject_id: null, class_id: null }]);
                          }
                        }}
                        className="h-3.5 w-3.5 rounded border-border accent-accent"
                      />
                      All Teachers ({staffList.length})
                    </label>
                  </div>
                  {!allTeachers && (
                    <button
                      type="button"
                      onClick={() => setTargetRows([...targetRows, { teacher_id: "", subject_id: null, class_id: null }])}
                      className="inline-flex h-7 items-center gap-1 rounded-field border border-border px-2 text-xs font-semibold text-muted-foreground transition hover:border-accent hover:text-accent"
                    >
                      <Plus className="h-3 w-3" /> Add Row
                    </button>
                  )}
                </div>
                <p className="mb-3 text-xs text-muted-foreground">Students only see teachers they actually study under — the server enforces this.</p>
                {allTeachers ? (
                  <div className="flex items-center justify-between rounded-field border border-accent/30 bg-accent/5 p-3 text-sm">
                    <div className="flex items-center gap-2 font-medium text-primary">
                      <CheckCircle2 className="h-4 w-4 text-accent shrink-0" />
                      <span>All Teachers selected ({staffList.length} teacher{staffList.length !== 1 ? "s" : ""} included)</span>
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        setAllTeachers(false);
                        setTargetRows([{ teacher_id: "", subject_id: null, class_id: null }]);
                      }}
                      className="text-xs font-semibold text-accent hover:underline"
                    >
                      Select Individually
                    </button>
                  </div>
                ) : (
                  <div className="space-y-2">
                    {targetRows.map((row, i) => (
                      <div key={i} className="flex gap-2 items-center">
                        <select
                          className={`${inputClass} flex-1`}
                          value={row.teacher_id}
                          onChange={(e) => {
                            if (e.target.value === "ALL") {
                              setAllTeachers(true);
                              return;
                            }
                            const updated = [...targetRows];
                            updated[i] = { ...row, teacher_id: e.target.value };
                            setTargetRows(updated);
                          }}
                        >
                          <option value="">— Select Teacher —</option>
                          <option value="ALL">All Teachers ({staffList.length})</option>
                          {staffList.map((s) => (
                            <option key={s.id} value={s.id}>{s.name}</option>
                          ))}
                        </select>
                        {targetRows.length > 1 && (
                          <button
                            type="button"
                            onClick={() => setTargetRows(targetRows.filter((_, j) => j !== i))}
                            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-field border border-border text-muted-foreground transition hover:border-destructive-border hover:text-destructive-text"
                          >
                            <X className="h-3.5 w-3.5" />
                          </button>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {createError && <p role="alert" className="text-sm text-destructive-text">{createError}</p>}

              <div className="flex flex-wrap gap-3 border-t border-border pt-4">
                <button
                  type="button"
                  onClick={() => setShowCreate(false)}
                  className="inline-flex h-10 items-center rounded-field border border-border px-4 text-sm font-semibold text-muted-foreground transition hover:border-accent hover:text-accent"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleCreate}
                  disabled={creating}
                  className="inline-flex h-10 items-center gap-2 rounded-field bg-accent px-5 text-sm font-semibold text-white shadow-accent transition hover:bg-accent-hover disabled:opacity-60"
                >
                  {creating && <Loader2 className="h-4 w-4 animate-spin" />}
                  {creating ? "Creating…" : "Create Campaign"}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Empty state when no campaigns */}
      {!loading && campaigns.length === 0 && !error && (
        <div className="mt-6 flex flex-col items-center py-8 text-center text-muted-foreground">
          <MessageSquareMore className="mb-3 h-10 w-10 opacity-30" />
          <p className="text-sm">No campaigns yet. Create your first to start collecting student feedback on teachers.</p>
        </div>
      )}
    </div>
  );
}

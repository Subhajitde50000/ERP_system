"use client";

import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ExternalLink, Eye, FileText, ImageIcon, Link2, Megaphone, Pin, Plus, X } from "lucide-react";

import { Card, EmptyState, PageHeader, inputClass, labelClass } from "@/components/admin/ui";
import { useResource } from "@/hooks/use-resource";
import {
  createPrincipalNotice,
  fetchPrincipalNotice,
  fetchPrincipalNotices,
  fetchPrincipalNoticeTargets,
  type PrincipalNoticeDetail,
  type PrincipalNoticeRow,
  type PrincipalNoticeTargets,
  type PrincipalPage,
} from "@/lib/principal";
import { API_BASE_URL } from "@/lib/auth";
import { AsyncState, dateTime, statusLabel } from "./principal-ui";

type PostScope = "INSTITUTION" | "DEPARTMENT" | "CLASS";
type LeadershipNoticeRow = Omit<PrincipalNoticeRow, "read_count" | "attachments"> & { read_count?: number; attachments?: PrincipalNoticeRow["attachments"] };
type LeadershipNoticeDetail = Omit<PrincipalNoticeDetail, "read_count" | "readers" | "attachments"> & {
  read_count?: number;
  readers?: PrincipalNoticeDetail["readers"];
  attachments?: PrincipalNoticeRow["attachments"];
};

export interface LeadershipNoticesConfig {
  title: string;
  subtitle: string;
  /** Omit for read-only boards (e.g. the mentor console) — hides the compose action. */
  composeHref?: string;
  canViewReadReceipts: boolean;
  canPin: boolean;
  allowAttachments?: boolean;
  allowedPostScopes: PostScope[];
  load: (filters: {
    query?: string;
    scope?: PostScope;
    includeExpired?: boolean;
    limit?: number;
    offset?: number;
  }) => Promise<PrincipalPage<LeadershipNoticeRow>>;
  loadDetail: (id: string) => Promise<LeadershipNoticeDetail>;
  loadTargets: () => Promise<PrincipalNoticeTargets>;
  create: (payload: {
    title: string;
    body: string;
    target_scope: PostScope;
    target_id?: string | null;
    priority: "NORMAL" | "IMPORTANT" | "URGENT";
    is_pinned: boolean;
    expires_at?: string | null;
    attachments?: Array<{ file_name: string; mime_type: string; data_url?: string; external_url?: string }>;
  }) => Promise<LeadershipNoticeDetail>;
}

const PRINCIPAL_NOTICE_CONFIG: LeadershipNoticesConfig = {
  title: "Notice board",
  subtitle: "All institution, department and class notices. Read receipts are available to the Principal.",
  composeHref: "/principal/notices/new",
  canViewReadReceipts: true,
  canPin: true,
  allowAttachments: true,
  allowedPostScopes: ["INSTITUTION", "DEPARTMENT", "CLASS"],
  load: fetchPrincipalNotices,
  loadDetail: fetchPrincipalNotice,
  loadTargets: fetchPrincipalNoticeTargets,
  create: createPrincipalNotice,
};

/** Shared C-PR-07 / C-VP-05 notice list; the server determines visibility. */
export function LeadershipNoticesPage({ config }: { config: LeadershipNoticesConfig }) {
  const [query, setQuery] = useState("");
  const [scope, setScope] = useState<"" | PostScope>("");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const resource = useResource(
    () => config.load({ query: query || undefined, scope: scope || undefined, limit: 100 }),
    [query, scope],
  );

  return (
    <div className="mx-auto max-w-5xl">
      <PageHeader
        title={config.title}
        subtitle={config.subtitle}
        action={config.composeHref ? <Link href={config.composeHref} className="inline-flex h-10 items-center gap-2 rounded-field bg-accent px-4 text-sm font-semibold text-white shadow-accent transition hover:bg-accent-hover"><Plus className="h-4 w-4" /> Post notice</Link> : undefined}
      />
      <Card className="mb-5 !p-4">
        <div className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_220px]">
          <div><label htmlFor="notice-search" className="sr-only">Search notices</label><input id="notice-search" type="search" value={query} onChange={(event) => setQuery(event.target.value)} className={inputClass} placeholder="Search notices" /></div>
          <div><label htmlFor="notice-scope" className="sr-only">Filter scope</label><select id="notice-scope" value={scope} onChange={(event) => setScope(event.target.value as typeof scope)} className={inputClass}><option value="">All visible scopes</option><option value="INSTITUTION">Institution-wide</option><option value="DEPARTMENT">Department</option><option value="CLASS">Class</option></select></div>
        </div>
      </Card>
      <AsyncState loading={resource.loading} error={resource.error} onRetry={resource.reload} loadingLabel="Loading notices…">
        {resource.data ? resource.data.items.length ? <div className="space-y-3">{resource.data.items.map((notice) => <NoticeCard key={notice.id} notice={notice} canViewReadReceipts={config.canViewReadReceipts} onOpen={() => setSelectedId(notice.id)} />)}</div> : <EmptyState text="No notices match this filter." /> : null}
      </AsyncState>
      {selectedId ? <NoticeDetail id={selectedId} config={config} onClose={() => setSelectedId(null)} /> : null}
    </div>
  );
}

/** Shared C-PR-08 / C-VP-06 composer. Scope choices come from role config. */
export function LeadershipNoticeComposerPage({ config }: { config: LeadershipNoticesConfig }) {
  const router = useRouter();
  const targets = useResource(config.loadTargets, []);
  const initialScope = config.allowedPostScopes[0]!;
  const [form, setForm] = useState({ title: "", body: "", targetScope: initialScope, targetId: "", priority: "NORMAL" as "NORMAL" | "IMPORTANT" | "URGENT", pinned: false, expiresAt: "", link: "" });
  const [files, setFiles] = useState<File[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const options = form.targetScope === "DEPARTMENT" ? targets.data?.departments ?? [] : form.targetScope === "CLASS" ? targets.data?.classes ?? [] : [];

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!form.title.trim() || !form.body.trim()) {
      setError("Enter a title and message.");
      return;
    }
    if (form.targetScope !== "INSTITUTION" && !form.targetId) {
      setError("Select the department or class receiving this notice.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const attachments: Array<{ file_name: string; mime_type: string; data_url?: string; external_url?: string }> = config.allowAttachments ? await Promise.all(files.map(async (file) => ({ file_name: file.name, mime_type: file.type || "application/octet-stream", data_url: await readFileAsDataUrl(file) }))) : [];
      if (config.allowAttachments && form.link.trim()) attachments.push({ file_name: form.link.trim(), mime_type: "text/uri-list", external_url: form.link.trim() });
      await config.create({
        title: form.title,
        body: form.body,
        target_scope: form.targetScope,
        target_id: form.targetScope === "INSTITUTION" ? null : form.targetId,
        priority: form.priority,
        is_pinned: config.canPin ? form.pinned : false,
        expires_at: form.expiresAt ? new Date(form.expiresAt).toISOString() : null,
        attachments,
      });
      router.replace((config.composeHref ?? "/").replace(/\/new$/, ""));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Could not publish this notice.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-3xl">
      <PageHeader title="Post notice" subtitle="Publish to the audiences this leadership role is delegated to. The server verifies every target." />
      <AsyncState loading={targets.loading} error={targets.error} onRetry={targets.reload} loadingLabel="Loading notice targets…">
        <Card>
          <form onSubmit={submit} className="space-y-5">
            <div><label htmlFor="notice-title" className={labelClass}>Title</label><input id="notice-title" className={inputClass} maxLength={255} value={form.title} onChange={(event) => setForm({ ...form, title: event.target.value })} required /></div>
            <div><label htmlFor="notice-body" className={labelClass}>Message</label><textarea id="notice-body" className={`${inputClass} min-h-44 py-3`} maxLength={20000} value={form.body} onChange={(event) => setForm({ ...form, body: event.target.value })} required /></div>
            {config.allowAttachments ? <div className="grid gap-4 sm:grid-cols-2"><div><label htmlFor="notice-files" className={labelClass}>Photos or documents</label><input id="notice-files" type="file" multiple accept="image/jpeg,image/png,image/webp,.pdf,.doc,.docx,.ppt,.pptx,.xls,.xlsx,.zip" className={inputClass} onChange={(event) => { const selected = Array.from(event.target.files ?? []); if (selected.length > 5 || selected.some((file) => file.size > 10 * 1024 * 1024)) { setError("Attach up to 5 files, each no larger than 10 MB."); return; } setFiles(selected); }} /><p className="mt-1 text-xs text-muted-foreground">PDF, Word, PowerPoint, Excel, ZIP, JPG, PNG or WebP; up to 10 MB each.</p>{files.length ? <p className="mt-2 text-xs text-muted-foreground">{files.map((file) => file.name).join(", ")}</p> : null}</div><div><label htmlFor="notice-link" className={labelClass}>External link (optional)</label><input id="notice-link" type="url" className={inputClass} placeholder="https://example.com" value={form.link} onChange={(event) => setForm({ ...form, link: event.target.value })} /></div></div> : null}
            <div className="grid gap-4 sm:grid-cols-2"><div><label htmlFor="notice-target-scope" className={labelClass}>Audience</label><select id="notice-target-scope" className={inputClass} value={form.targetScope} onChange={(event) => setForm({ ...form, targetScope: event.target.value as PostScope, targetId: "" })}>{config.allowedPostScopes.map((postScope) => <option key={postScope} value={postScope}>{postScope === "INSTITUTION" ? "Institution-wide" : postScope === "DEPARTMENT" ? "Department" : "Class"}</option>)}</select></div><div><label htmlFor="notice-priority" className={labelClass}>Priority</label><select id="notice-priority" className={inputClass} value={form.priority} onChange={(event) => setForm({ ...form, priority: event.target.value as typeof form.priority })}><option value="NORMAL">Normal</option><option value="IMPORTANT">Important</option><option value="URGENT">Urgent</option></select></div></div>
            {form.targetScope !== "INSTITUTION" ? <div><label htmlFor="notice-target" className={labelClass}>{form.targetScope === "DEPARTMENT" ? "Department" : "Class"}</label><select id="notice-target" className={inputClass} value={form.targetId} onChange={(event) => setForm({ ...form, targetId: event.target.value })} required><option value="">Select {form.targetScope.toLowerCase()}</option>{options.map((option) => <option key={option.id} value={option.id}>{option.department_name ? `${option.department_name} · ${option.name}` : option.name}</option>)}</select></div> : null}
            <div className="grid gap-4 sm:grid-cols-2"><div><label htmlFor="notice-expires" className={labelClass}>Expires at (optional)</label><input id="notice-expires" type="datetime-local" className={inputClass} value={form.expiresAt} onChange={(event) => setForm({ ...form, expiresAt: event.target.value })} /></div>{config.canPin ? <label className="flex items-center gap-2 pt-7 text-sm font-medium text-primary"><input type="checkbox" checked={form.pinned} onChange={(event) => setForm({ ...form, pinned: event.target.checked })} className="h-4 w-4 rounded border-border accent-accent" /> Pin this notice</label> : <p className="pt-7 text-xs text-muted-foreground">Only institution leadership can pin notices.</p>}</div>
            {error ? <p role="alert" className="text-sm text-destructive-text">{error}</p> : null}
            <div className="flex flex-wrap gap-3"><button type="submit" disabled={busy} className="inline-flex h-11 items-center gap-2 rounded-field bg-accent px-5 text-sm font-semibold text-white shadow-accent transition hover:bg-accent-hover disabled:opacity-60"><Megaphone className="h-4 w-4" /> {busy ? "Publishing…" : "Publish notice"}</button><Link href={(config.composeHref ?? "/").replace(/\/new$/, "")} className="inline-flex h-11 items-center rounded-field border border-border px-5 text-sm font-semibold text-muted-foreground hover:border-accent hover:text-accent">Cancel</Link></div>
          </form>
        </Card>
      </AsyncState>
    </div>
  );
}

/** C-PR-07 / C-PR-08 wrappers. */
export function PrincipalNoticesPage() {
  return <LeadershipNoticesPage config={PRINCIPAL_NOTICE_CONFIG} />;
}

export function PrincipalNoticeComposerPage() {
  return <LeadershipNoticeComposerPage config={PRINCIPAL_NOTICE_CONFIG} />;
}

function NoticeCard({ notice, canViewReadReceipts, onOpen }: { notice: LeadershipNoticeRow; canViewReadReceipts: boolean; onOpen: () => void }) {
  const priorityClass = { NORMAL: "bg-muted text-muted-foreground", IMPORTANT: "bg-warning-light text-warning-text", URGENT: "bg-destructive-light text-destructive-text" }[notice.priority];
  return (
    <Card className={notice.is_pinned ? "border-accent-border" : ""}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="mb-2 flex flex-wrap items-center gap-2">
            {notice.is_pinned ? <span className="inline-flex items-center gap-1 rounded-full bg-accent-light px-2.5 py-1 text-[11px] font-bold text-accent"><Pin className="h-3 w-3" /> Pinned</span> : null}
            <span className={`rounded-full px-2.5 py-1 text-[11px] font-bold ${priorityClass}`}>{statusLabel(notice.priority)}</span>
            <span className="rounded-full bg-muted px-2.5 py-1 text-[11px] font-bold text-muted-foreground">{notice.target_name ?? statusLabel(notice.target_scope)}</span>
          </div>
          <h2 className="font-display text-base font-bold text-primary">{notice.title}</h2>
          <p className="mt-2 line-clamp-2 whitespace-pre-wrap text-sm text-muted-foreground">{notice.body}</p>
          <p className="mt-3 text-xs text-muted-foreground">By {notice.author_name ?? "Deleted user"} · {dateTime(notice.published_at)}</p>
        </div>
        <button type="button" onClick={onOpen} className="inline-flex h-9 shrink-0 items-center gap-1.5 rounded-field border border-border px-3 text-xs font-semibold text-foreground transition hover:border-accent hover:text-accent"><Eye className="h-3.5 w-3.5" /> {canViewReadReceipts ? `${notice.read_count ?? 0} read` : "View"}</button>
      </div>
    </Card>
  );
}

function NoticeDetail({ id, config, onClose }: { id: string; config: LeadershipNoticesConfig; onClose: () => void }) {
  const resource = useResource(() => config.loadDetail(id), [id]);
  return (
    <div role="dialog" aria-modal="true" aria-label="Notice details" className="fixed inset-0 z-50 flex items-center justify-center bg-primary/50 p-4">
      <div className="max-h-[90vh] w-full max-w-2xl overflow-y-auto rounded-card bg-white p-5 shadow-2xl sm:p-6">
        <div className="mb-5 flex items-center justify-between gap-3"><h2 className="font-display text-lg font-bold text-primary">Notice details</h2><button type="button" onClick={onClose} aria-label="Close notice" className="rounded-lg p-2 text-muted-foreground hover:bg-muted hover:text-primary"><X className="h-4 w-4" /></button></div>
        <AsyncState loading={resource.loading} error={resource.error} onRetry={resource.reload} loadingLabel="Loading notice…">
          {resource.data ? <NoticeDetailContent notice={resource.data} canViewReadReceipts={config.canViewReadReceipts} /> : null}
        </AsyncState>
      </div>
    </div>
  );
}

function NoticeDetailContent({ notice, canViewReadReceipts }: { notice: LeadershipNoticeDetail; canViewReadReceipts: boolean }) {
  const readers = notice.readers ?? [];
  return (
    <div>
      <div className="border-b border-border pb-4"><h3 className="font-display text-xl font-bold text-primary">{notice.title}</h3><p className="mt-2 text-xs text-muted-foreground">{notice.target_name ?? statusLabel(notice.target_scope)} · posted {dateTime(notice.published_at)}</p></div>
      <p className="whitespace-pre-wrap py-5 text-sm leading-6 text-foreground">{notice.body}</p>
      {notice.attachments?.length ? <div className="border-t border-border py-5"><h4 className="mb-3 font-display text-base font-bold text-primary">Attachments</h4><div className="grid gap-3 sm:grid-cols-2">{notice.attachments.map((attachment) => attachment.is_image ? <a key={attachment.id} href={attachmentUrl(attachment.url)} target="_blank" rel="noreferrer" className="overflow-hidden rounded-field border border-border"><img src={attachmentUrl(attachment.url)} alt={attachment.file_name} className="h-40 w-full object-cover" /><span className="flex items-center gap-2 p-2 text-xs font-medium"><ImageIcon className="h-4 w-4" />{attachment.file_name}</span></a> : <a key={attachment.id} href={attachmentUrl(attachment.url)} target="_blank" rel="noreferrer" className="flex items-center gap-2 rounded-field border border-border p-3 text-sm font-medium text-accent hover:border-accent">{attachment.is_link ? <Link2 className="h-4 w-4 shrink-0" /> : <FileText className="h-4 w-4 shrink-0" />}{attachment.file_name}<ExternalLink className="ml-auto h-4 w-4 shrink-0" /></a>)}</div></div> : null}
      {canViewReadReceipts ? <><h4 className="border-t border-border pt-5 font-display text-base font-bold text-primary">Read receipts ({readers.length})</h4>{readers.length ? <ul className="mt-3 divide-y divide-border rounded-field border border-border">{readers.map((reader) => <li key={reader.id} className="flex items-center justify-between gap-3 px-3 py-3 text-sm"><span className="font-medium text-primary">{reader.name}</span><time className="text-xs text-muted-foreground">{dateTime(reader.read_at)}</time></li>)}</ul> : <p className="mt-3 text-sm text-muted-foreground">No recipients have read this notice yet.</p>}</> : null}
    </div>
  );
}

function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => { const reader = new FileReader(); reader.onerror = () => reject(new Error(`Could not read ${file.name}.`)); reader.onload = () => resolve(String(reader.result)); reader.readAsDataURL(file); });
}

function attachmentUrl(url: string) {
  return url.startsWith("/") ? `${API_BASE_URL}${url}` : url;
}

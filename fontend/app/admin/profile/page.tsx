"use client";

import { useCallback, useEffect, useState } from "react";

import { Card, ErrorState, Loading, PageHeader, inputClass, labelClass } from "@/components/admin/ui";
import { fetchProfile, updateProfile, type InstitutionProfile } from "@/lib/institution";

const FIELDS: { key: keyof InstitutionProfile; label: string }[] = [
  { key: "name", label: "Institution name" },
  { key: "email", label: "Email" },
  { key: "phone", label: "Phone" },
  { key: "address", label: "Address" },
  { key: "city", label: "City" },
  { key: "state", label: "State" },
  { key: "pincode", label: "Pincode" },
  { key: "website", label: "Website" },
  { key: "logo_url", label: "Logo URL" },
];

export default function ProfilePage() {
  const [profile, setProfile] = useState<InstitutionProfile | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setProfile(await fetchProfile());
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load the profile.");
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  async function save(e: React.FormEvent) {
    e.preventDefault();
    if (!profile) return;
    setBusy(true);
    setMsg(null);
    try {
      const patch: Record<string, string> = {};
      for (const f of FIELDS) {
        const v = profile[f.key];
        if (v != null) patch[f.key] = String(v);
      }
      setProfile(await updateProfile(patch));
      setMsg("Profile updated.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not update the profile.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl">
      <PageHeader title="Institution Profile" subtitle="Public details for your institution." />
      {error ? <div className="mb-4"><ErrorState message={error} /></div> : null}
      {!profile ? <Loading /> : (
        <>
          <Card className="mb-6">
            <div className="flex flex-wrap items-center gap-4">
              <div>
                <p className="font-display text-lg font-bold text-primary">{profile.name}</p>
                <p className="text-xs text-muted-foreground">
                  {profile.slug}.shikshasync.me · {profile.type}
                </p>
              </div>
              <div className="ml-auto text-right text-xs text-muted-foreground">
                <p>Plan: <span className="font-semibold text-foreground">{profile.plan_name ?? "—"}</span></p>
                <p>Subscription: <span className="font-semibold text-foreground">{profile.subscription_status ?? "—"}</span></p>
              </div>
            </div>
          </Card>

          <Card>
            <form onSubmit={save} className="grid gap-4 sm:grid-cols-2">
              {FIELDS.map((f) => (
                <div key={f.key} className={f.key === "address" || f.key === "name" ? "sm:col-span-2" : ""}>
                  <label className={labelClass}>{f.label}</label>
                  <input
                    className={inputClass}
                    value={(profile[f.key] as string) ?? ""}
                    onChange={(e) => setProfile({ ...profile, [f.key]: e.target.value })}
                  />
                </div>
              ))}
              {msg ? <p className="text-xs font-medium text-success-text sm:col-span-2">{msg}</p> : null}
              <div className="sm:col-span-2">
                <button type="submit" disabled={busy} className="inline-flex h-11 items-center justify-center rounded-field bg-accent px-5 text-sm font-semibold text-white shadow-accent transition hover:bg-accent-hover disabled:opacity-60">
                  {busy ? "Saving…" : "Save profile"}
                </button>
              </div>
            </form>
          </Card>
        </>
      )}
    </div>
  );
}

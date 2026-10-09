import React, { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import {
  Cloud,
  FileText,
  GithubLogo,
  GlobeHemisphereWest,
  MagnifyingGlass,
  Scan,
} from "@phosphor-icons/react";
import { api } from "@/lib/api";
import { matchStrength } from "@/lib/readiness";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

const SURFACE_META = {
  documents: { icon: FileText, label: "Documents" },
  cloud: { icon: Cloud, label: "Cloud" },
  code: { icon: GithubLogo, label: "Code" },
  web: { icon: GlobeHemisphereWest, label: "Web" },
};

// "samples" is not a failure: the surface is still scanned and suggested, but a bound
// collector will store a labeled sample until credentials exist.
const STATE_LABEL = { active: "Active", samples: "Samples", idle: "Not found", planned: "Planned" };

function SurfaceStrip({ surfaces }) {
  return (
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {surfaces.map((s) => {
        const m = SURFACE_META[s.surface] ?? { icon: FileText, label: s.surface };
        const Icon = m.icon;
        const count = s.documents ?? s.descriptors;
        return (
          <Card key={s.surface} className={s.state === "active" ? "" : "opacity-70"}>
            <CardContent className="flex items-start gap-3 pt-5">
              <span className="grid size-9 shrink-0 place-items-center rounded-lg bg-accent text-accent-foreground">
                <Icon size={18} weight="duotone" aria-hidden />
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-medium">{m.label}</span>
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {STATE_LABEL[s.state] ?? "Planned"}
                  </span>
                </div>
                <p className="mt-1 truncate text-xs text-muted-foreground" title={s.detail || s.root}>
                  {count != null
                    ? `${count} ${s.surface === "documents" ? "document" : "descriptor"}${count === 1 ? "" : "s"}`
                    : s.detail}
                </p>
              </div>
            </CardContent>
          </Card>
        );
      })}
    </div>
  );
}

function CandidateRow({ cand, busy, onBind }) {
  return (
    <li className="flex items-start gap-3 py-3">
      <span className="w-14 shrink-0 pt-0.5 font-mono text-xs text-muted-foreground">
        {cand.control_code}
      </span>
      <div className="min-w-0 flex-1">
        <div className="truncate font-mono text-sm" title={cand.source_name}>
          {cand.source_name}
        </div>
        {/* The reason names the signals that matched — the auditor can check the
            claim instead of trusting a score. */}
        <div className="mt-0.5 text-xs text-pretty text-muted-foreground">{cand.reason}</div>
        <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
          <span className="rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium">
            {matchStrength(cand.score)}
          </span>
          <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground">
            {cand.surface}
          </span>
          {cand.signals?.age_days != null && (
            <span className="text-[11px] text-muted-foreground">
              {cand.signals.age_days}d old
            </span>
          )}
        </div>
      </div>
      <Button size="sm" variant="outline" disabled={busy} onClick={() => onBind(cand)}>
        {busy ? "Binding…" : "Bind"}
      </Button>
    </li>
  );
}

export default function Discovery({ controls, onBound }) {
  const [sources, setSources] = useState(null);
  const [candidates, setCandidates] = useState(null);
  const [summary, setSummary] = useState(null);
  const [scanning, setScanning] = useState(false);
  const [binding, setBinding] = useState(() => new Set());

  const load = useCallback(async () => {
    const [src, cand] = await Promise.all([
      api("/discovery/sources").catch(() => null),
      api("/discovery/candidates").catch(() => null),
    ]);
    if (src) setSources(src.surfaces);
    setCandidates(Array.isArray(cand) ? cand : []);
  }, []);

  useEffect(() => { load(); }, [load]);

  const scan = async () => {
    setScanning(true);
    const r = await api("/discovery/scan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    }).catch(() => null);
    setScanning(false);
    if (!r) { toast.error("Scan failed."); return; }
    setSummary(r);
    await load();
    const parts = [`${r.documents} documents`, `${r.descriptors} descriptors`,
                   ...(r.pages ? [`${r.pages} pages`] : [])];
    toast.success(
      r.candidates
        ? `Found ${r.candidates} suggestion${r.candidates === 1 ? "" : "s"} across ${parts.join(", ")}.`
        : `Scanned ${parts.join(", ")} — no new suggestions.`
    );
  };

  const bind = async (cand) => {
    setBinding((p) => new Set(p).add(cand.id));
    const r = await api("/discovery/bind", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ candidate_id: cand.id }),
    }).catch(() => null);
    setBinding((p) => { const n = new Set(p); n.delete(cand.id); return n; });
    if (!r || !r.binding_id) { toast.error("Couldn't bind that candidate."); return; }
    toast.success(`Mapped ${cand.source_name} to ${cand.control_code}.`);
    await load();
    onBound?.();
  };

  if (candidates === null || sources === null) {
    return (
      <div className="space-y-2">
        <Skeleton className="h-20 w-full" />
        <Skeleton className="h-32 w-full" />
      </div>
    );
  }

  // What the last scan actually looked at. Pages only appear once a web surface is
  // configured, so an unconfigured run doesn't report a misleading "+ 0 pages".
  const scanned = summary
    ? [`${summary.documents} documents`, `${summary.descriptors} descriptors`,
       ...(summary.pages ? [`${summary.pages} pages`] : [])].join(" + ")
    : null;

  // Group by control, preserving the API's best-first order.
  const groups = [];
  const byControl = new Map();
  for (const c of candidates) {
    if (!byControl.has(c.control_id)) {
      const g = { key: c.control_id, code: c.control_code, name: c.control_name, items: [] };
      byControl.set(c.control_id, g);
      groups.push(g);
    }
    byControl.get(c.control_id).items.push(c);
  }
  const covered = groups.length;
  const total = controls?.length ?? 0;

  return (
    <div className="space-y-4">
      <p className="max-w-[70ch] border-l-2 border-primary pl-4 text-sm text-pretty text-muted-foreground">
        The engine scans your configured surfaces for artifacts that look like evidence for each
        control, then suggests matches <em>with the signals that matched</em>. Nothing is collected
        until you confirm a suggestion — binding only maps the collector.
      </p>

      <SurfaceStrip surfaces={sources} />

      <Card>
        <CardContent className="flex flex-wrap items-center gap-3 pt-5">
          <Button onClick={scan} disabled={scanning}>
            <Scan size={16} />
            {scanning ? "Scanning…" : "Run discovery"}
          </Button>
          <p className="min-w-0 flex-1 text-sm text-muted-foreground">
            {summary
              ? `Last scan: ${scanned} → ${summary.candidates} suggestions.`
              : total
                ? `${covered} of ${total} controls have suggestions.`
                : "Load a checklist first, then scan."}
          </p>
        </CardContent>
      </Card>

      {groups.length === 0 ? (
        <div className="grid place-items-center rounded-xl border border-dashed border-input bg-card px-6 py-14 text-center">
          <div className="max-w-md">
            <MagnifyingGlass size={28} className="mx-auto text-muted-foreground" />
            <h2 className="mt-3 text-base font-semibold">No suggestions yet</h2>
            <p className="mt-1.5 text-sm text-pretty text-muted-foreground">
              {total
                ? "Run discovery to scan your surfaces for candidate evidence."
                : "Load the SOC 2 starter checklist, then run discovery."}
            </p>
          </div>
        </div>
      ) : (
        <div className="space-y-3.5">
          {groups.map((g) => (
            <Card key={g.key}>
              <CardContent className="pt-5">
                <div className="flex items-baseline gap-2">
                  <span className="font-mono text-xs text-muted-foreground">{g.code}</span>
                  <span className="min-w-0 flex-1 truncate text-sm font-medium">{g.name}</span>
                  <span className="shrink-0 text-xs text-muted-foreground tabular">
                    {g.items.length} suggestion{g.items.length === 1 ? "" : "s"}
                  </span>
                </div>
                <ul className="-my-1 mt-1 divide-y divide-border">
                  {g.items.map((c) => (
                    <CandidateRow
                      key={c.id}
                      cand={c}
                      busy={binding.has(c.id)}
                      onBind={bind}
                    />
                  ))}
                </ul>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}

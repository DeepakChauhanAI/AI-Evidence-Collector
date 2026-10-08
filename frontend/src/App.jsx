import React, { useEffect, useState, useCallback, useRef } from "react";
import { toast } from "sonner";
import {
  DownloadSimple,
  ShieldCheck,
  UploadSimple,
  ArrowClockwise,
  Sparkle,
  DotsThree,
  PlugsConnected,
} from "@phosphor-icons/react";

import { api, exportUrl } from "./lib/api.js";
import { readiness } from "./lib/readiness.js";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Toaster } from "@/components/ui/sonner";import AppSidebar from "@/components/app-sidebar.jsx";
import MobileNav from "@/components/mobile-nav.jsx";
import PageHeader from "@/components/page-header.jsx";
import BindModal from "./components/BindModal.jsx";
import Dashboard from "./views/Dashboard.jsx";
import Controls from "./views/Controls.jsx";
import Evidence from "./views/Evidence.jsx";
import Activity from "./views/Activity.jsx";
import Sources from "./views/Sources.jsx";

const HEADS = {
  dashboard: ["Audit Readiness", "Where you stand against the SOC 2 checklist, at a glance."],
  controls: ["Evidence Checklist", "Map an automated collector to each control. Collectors pull evidence on schedule."],
  evidence: ["Evidence Library", "Every artifact collected — searchable, hashed, and traceable to its control."],
  activity: ["Collection Activity", "Every run and the evidence it produced, newest first."],
  sources: ["Collector Sources", "The shared workers that gather evidence — a few, each serving many controls."],
};

/* ---------- token gate ---------- */
function Gate({ onSave }) {
  const [val, setVal] = useState("");
  return (
    <div className="grid min-h-dvh place-items-center bg-muted/50 p-5">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          onSave(val.trim());
        }}
        className="w-full max-w-sm rounded-xl border border-border bg-card p-7 shadow-e2"
      >
        <h1 className="text-lg font-semibold tracking-tight">Connect to your workspace</h1>
        <p className="mt-1 mb-5 text-sm text-muted-foreground">
          Paste the API token configured as <code className="font-mono text-xs">API_TOKEN</code> on the server.
        </p>
        <Label htmlFor="tok">API token</Label>
        <Input
          id="tok"
          autoFocus
          className="mt-1.5 mb-4"
          value={val}
          onChange={(e) => setVal(e.target.value)}
          placeholder="Paste your token"
        />
        <Button type="submit" className="w-full">
          Connect
        </Button>
      </form>
    </div>
  );
}

/* ---------- app ---------- */
export default function App() {
  const [authed, setAuthed] = useState(true);
  const [view, setView] = useState("dashboard");
  const [controls, setControls] = useState([]);
  const [collectors, setCollectors] = useState([]);
  const [runs, setRuns] = useState([]);
  const [binding, setBinding] = useState(null);
  const [selected, setSelected] = useState(null); // control open in the drill-down sheet
  const [evidenceCount, setEvidenceCount] = useState(null);
  // Sidebar collapse is a workspace preference, not per-visit — persist it so it
  // survives a reload instead of snapping back open.
  const [collapsed, setCollapsed] = useState(() => localStorage.getItem("sidebar_collapsed") === "1");
  const csvInput = useRef(null);

  // Adapts the old string-based toast contract (BindModal still calls it that
  // way) onto sonner, promoting the ✓/⚠ prefixes to real variants so the
  // glyphs stop being part of the message text.
  const toastMsg = useCallback((msg) => {
    const s = String(msg ?? "");
    if (s.startsWith("⚠")) toast.warning(s.slice(1).trim());
    else if (s.startsWith("✓")) toast.success(s.slice(1).trim());
    else toast(s);
  }, []);

  const refresh = useCallback(async () => {
    try {
      const [c, r, col, ev] = await Promise.all([
        api("/controls"), api("/runs"), api("/collectors"), api("/evidence").catch(() => null),
      ]);
      setControls(c); setRuns(r); setCollectors(col); setAuthed(true);
      if (Array.isArray(ev)) setEvidenceCount(ev.length);
    } catch { setAuthed(false); }
  }, []);

  useEffect(() => { refresh(); }, [refresh]);

  useEffect(() => {
    localStorage.setItem("sidebar_collapsed", collapsed ? "1" : "0");
  }, [collapsed]);

  const saveToken = (t) => { if (t) { localStorage.setItem("api_token", t); refresh(); } };

  const seed = async () => {
    const r = await api("/checklist/seed", { method: "POST" });
    await refresh();
    toastMsg(r.created ? `Loaded ${r.created} SOC 2 controls.` : "Starter controls already loaded.");
  };

  const importCsv = async (e) => {
    const file = e.target.files[0]; if (!file) return;
    const fd = new FormData(); fd.append("file", file);
    const r = await api("/checklist/import", { method: "POST", body: fd }).catch(() => null);
    e.target.value = "";
    if (Array.isArray(r)) { await refresh(); toastMsg(`Imported ${r.length} controls.`); }
    else toastMsg("Import failed — CSV needs code and name columns.");
  };

  const run = async (id) => { toast("Collecting…"); await api(`/bindings/${id}/run`, { method: "POST" }); await refresh(); };

  // Recollect every binding on controls that are stale or failed — close the freshness loop in one click.
  const runStale = async (ids) => {
    toast(`Recollecting ${ids.length}…`);
    for (const id of ids) await api(`/bindings/${id}/run`, { method: "POST" }).catch(() => null);
    await refresh();
    toastMsg(`Recollected ${ids.length} collector${ids.length === 1 ? "" : "s"}.`);
  };

  // Re-verify chain of custody on demand: re-hash every stored file, compare to capture.
  const verifyIntegrity = async () => {
    toast("Verifying evidence…");
    const r = await api("/integrity").catch(() => null);
    if (!r) { toast.error("Integrity check failed."); return; }
    const { ok, tampered, missing } = r.counts;
    toastMsg(tampered || missing
      ? `⚠ ${tampered} tampered, ${missing} missing (${ok} intact).`
      : `✓ All ${ok} evidence files intact.`);
  };

  const openControl = (c) => { setSelected(c); setView("controls"); };

  if (!authed) return <Gate onSave={saveToken} />;

  const ready = readiness(controls, runs);
  const tally = { satisfied: 0, gap: 0, collected: 0, stale: 0, pending: 0, failed: 0, uncovered: 0 };
  for (const c of controls) tally[(ready[c.id] || { status: "uncovered" }).status]++;
  const staleIds = controls
    .filter((c) => ["stale", "failed"].includes((ready[c.id] || {}).status))
    .flatMap((c) => c.bindings.map((b) => b.id));

  const counts = { dashboard: null, controls: controls.length, evidence: evidenceCount,
                   activity: runs.length, sources: collectors.length };

  const [title, description] = HEADS[view];

  const headerActions = view === "controls" && (
    <>
      <Button variant="outline" onClick={verifyIntegrity}>
        <ShieldCheck size={16} />
        Verify integrity
      </Button>
      <Button asChild>
        <a href={exportUrl()}>
          <DownloadSimple size={16} />
          Export for audit
        </a>
      </Button>
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" size="icon" aria-label="More actions">
            <DotsThree size={18} weight="bold" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-56">
          <DropdownMenuItem onSelect={() => csvInput.current?.click()}>
            <UploadSimple size={16} />
            Import checklist CSV
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={seed}>
            <Sparkle size={16} />
            Load SOC 2 starter
          </DropdownMenuItem>
          {staleIds.length > 0 && (
            <>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={() => runStale(staleIds)}>
                <ArrowClockwise size={16} />
                Recollect stale ({staleIds.length})
              </DropdownMenuItem>
            </>
          )}
        </DropdownMenuContent>
      </DropdownMenu>
    </>
  );

  return (
    <>
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:top-3 focus:left-3 focus:z-50 focus:rounded-md focus:bg-primary focus:px-4 focus:py-2 focus:text-sm focus:text-primary-foreground"
      >
        Skip to content
      </a>

      <div className="flex min-h-dvh bg-muted/30">
        <AppSidebar
          view={view}
          onNavigate={setView}
          counts={counts}
          collapsed={collapsed}
          onToggle={() => setCollapsed((c) => !c)}
        />

        <div className="flex min-w-0 flex-1 flex-col bg-background">
          <div className="flex items-center gap-2 border-b border-border px-3 py-2 lg:hidden">
            <MobileNav view={view} onNavigate={setView} counts={counts} />
            <img src="/panacea_icon.svg" alt="Panacea InfoSec" className="size-5 rounded object-contain" />
            <span className="text-sm font-semibold tracking-tight">Panacea InfoSec</span>
          </div>

          <PageHeader title={title} description={description} actions={headerActions} />

          <main id="main" className="flex-1 px-5 py-6 sm:px-8">
            {view === "dashboard" && (
              <Dashboard controls={controls} runs={runs} ready={ready} tally={tally}
                         onRecollect={runStale} staleIds={staleIds} onSelect={openControl}
                         onNavigate={setView} />
            )}
            {view === "controls" && (
              controls.length ? (
                <Controls controls={controls} runs={runs} ready={ready} collectors={collectors}
                          onRun={run} onBind={setBinding} selected={selected} onSelect={setSelected} />
              ) : (
                <div className="grid place-items-center rounded-xl border border-dashed border-input bg-card px-6 py-14 text-center">
                  <div className="max-w-md">
                    <PlugsConnected size={28} className="mx-auto text-muted-foreground" />
                    <h2 className="mt-3 text-base font-semibold">No controls yet</h2>
                    <p className="mt-1.5 mb-5 text-sm text-pretty text-muted-foreground">
                      Load the built-in SOC 2 starter checklist to begin, or import your own export from a GRC tool as CSV.
                    </p>
                    <Button onClick={seed}>Load SOC 2 starter</Button>
                  </div>
                </div>
              )
            )}
            {view === "evidence" && <Evidence />}
            {view === "activity" && <Activity runs={runs} />}
            {view === "sources" && <Sources collectors={collectors} controls={controls} />}
          </main>
        </div>
      </div>

      <input ref={csvInput} type="file" accept=".csv" onChange={importCsv} className="hidden" />

      {binding && (
        <BindModal control={binding} collectors={collectors}
                   onClose={() => setBinding(null)} onSaved={refresh} toast={toastMsg} />
      )}

      <Toaster position="bottom-center" />
    </>
  );
}

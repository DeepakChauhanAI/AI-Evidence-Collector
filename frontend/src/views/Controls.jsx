import React, { useEffect, useMemo, useState } from "react";
import { toast } from "sonner";
import {
  CaretRight,
  Warning,
  Plus,
  Play,
  Eye,
  DownloadSimple,
  Sparkle,
} from "@phosphor-icons/react";
import EvidencePreviewModal from "@/components/EvidencePreviewModal";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Progress } from "@/components/ui/progress";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "@/components/ui/collapsible";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
  SheetDescription,
} from "@/components/ui/sheet";
import StatusBadge from "@/components/status-badge";
import { STALE_DAYS, groupControls, matchFilter, matchStrength } from "@/lib/readiness";
import { api, downloadUrl } from "@/lib/api";
import { cn } from "@/lib/utils";

const FILTERS = [
  ["all", "All"], ["gaps", "Gaps"], ["stale", "Stale"], ["satisfied", "Satisfied"], ["uncovered", "Uncovered"],
];
const READY = ["satisfied", "collected"];

export default function Controls({ controls, runs, ready, collectors, onRun, onBind, onBound, selected, onSelect }) {
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState("all");
  const [open, setOpen] = useState(() => new Set());
  // Discovery suggestions, fetched here so the checklist itself shows what the
  // engine already found — the auditor shouldn't have to visit another view to
  // learn a control has evidence waiting.
  const [suggestions, setSuggestions] = useState([]);

  const loadSuggestions = () =>
    api("/discovery/candidates").catch(() => []).then((r) => setSuggestions(Array.isArray(r) ? r : []));

  useEffect(() => { loadSuggestions(); }, []);

  const byControl = useMemo(() => {
    const m = new Map();
    for (const s of suggestions) {
      if (!m.has(s.control_id)) m.set(s.control_id, []);
      m.get(s.control_id).push(s);
    }
    return m;
  }, [suggestions]);

  // Confirming a suggestion creates an ordinary binding — same path as manual entry.
  const bindSuggestion = async (s) => {
    const r = await api("/discovery/bind", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ candidate_id: s.id }),
    }).catch(() => null);
    if (!r?.binding_id) { toast.error("Couldn't bind that suggestion."); return; }
    toast.success(`Mapped ${s.source_name} to ${s.control_code}.`);
    await loadSuggestions();
    onBound?.();
  };

  const visible = controls.filter((c) => matchFilter(c, ready[c.id], q, filter));
  const groups = groupControls(visible);

  // While a search or filter is active every group is forced open — otherwise
  // filtered results stay hidden behind a collapsed header and the screen looks
  // empty. With no filter, the user's own toggles win.
  const filtering = q.trim() !== "" || filter !== "all";
  const isOpen = (key) => filtering || open.has(key);

  const toggle = (key) =>
    setOpen((prev) => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });

  return (
    <>
      <div className="mb-4 flex flex-wrap items-center gap-2">
        <Input
          placeholder="Search controls by code, name, or description…"
          value={q}
          onChange={(e) => setQ(e.target.value)}
          className="h-9 min-w-[200px] flex-1"
          aria-label="Search controls"
        />
        <ToggleGroup
          type="single"
          value={filter}
          onValueChange={(v) => v && setFilter(v)}
          variant="outline"
          size="sm"
        >
          {FILTERS.map(([key, label]) => (
            <ToggleGroupItem key={key} value={key} aria-label={`Show ${label.toLowerCase()} controls`}>
              {label}
            </ToggleGroupItem>
          ))}
        </ToggleGroup>
      </div>

      {visible.length === 0 ? (
        <div className="grid place-items-center rounded-xl border border-dashed border-input bg-card px-6 py-14 text-center">
          <div className="max-w-sm">
            <h2 className="text-base font-semibold">No matching controls</h2>
            <p className="mt-1.5 text-sm text-muted-foreground">
              Adjust the search or filter to see controls.
            </p>
          </div>
        </div>
      ) : (
        <div className="space-y-3">
          {groups.map((g) => {
            const rdy = g.controls.filter((c) => READY.includes((ready[c.id] || {}).status)).length;
            const gpct = Math.round((rdy / g.controls.length) * 100);
            const opened = isOpen(g.key);
            return (
              <Collapsible key={g.key} open={opened} onOpenChange={() => toggle(g.key)}>
                <div className="overflow-hidden rounded-xl border border-border bg-card">
                  <CollapsibleTrigger asChild>
                    <button
                      type="button"
                      className="flex w-full items-center gap-3 px-4 py-3 text-left transition-colors hover:bg-muted/50 focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
                    >
                      <CaretRight
                        size={14}
                        className={cn("shrink-0 text-muted-foreground transition-transform", opened && "rotate-90")}
                        aria-hidden
                      />
                      <span className="min-w-0 flex-1 truncate text-sm font-medium">
                        <span className="font-mono text-xs text-muted-foreground">{g.key}</span>{" "}
                        {g.name}
                      </span>
                      <Progress value={gpct} className="hidden h-1.5 w-32 sm:block" />
                      <span className="shrink-0 text-xs text-muted-foreground tabular">
                        {rdy}/{g.controls.length}
                      </span>
                    </button>
                  </CollapsibleTrigger>

                  <CollapsibleContent>
                    <ul className="divide-y divide-border border-t border-border">
                      {g.controls.map((c) => {
                        const st = ready[c.id] || { status: "uncovered" };
                        return (
                          <li key={c.id} className="px-4 py-3.5 transition-colors hover:bg-muted/30">
                            <div className="flex flex-col gap-3 sm:flex-row sm:items-start">
                              <button
                                type="button"
                                onClick={() => onSelect(c)}
                                className="min-w-0 flex-1 text-left"
                              >
                                <div className="flex flex-wrap items-center gap-2">
                                  <span className="font-mono text-xs text-muted-foreground">
                                    {c.code}
                                  </span>
                                  <span className="text-sm font-medium">{c.name}</span>
                                  <StatusBadge status={st.status} size="sm" />
                                </div>
                                {c.description && (
                                  <p className="mt-1 line-clamp-2 text-sm text-pretty text-muted-foreground">
                                    {c.description}
                                  </p>
                                )}
                                {st.status === "gap" && st.a?.gaps && (
                                  <p className="mt-1.5 flex items-start gap-1.5 text-sm text-status-gap">
                                    <Warning size={14} weight="fill" className="mt-0.5 shrink-0" aria-hidden />
                                    {st.a.gaps}
                                  </p>
                                )}
                                {st.status === "stale" && (
                                  <p className="mt-1.5 flex items-start gap-1.5 text-sm text-status-stale">
                                    <Warning size={14} weight="fill" className="mt-0.5 shrink-0" aria-hidden />
                                    Evidence is older than {STALE_DAYS} days — recollect for the current audit period.
                                  </p>
                                )}
                              </button>

                              <div className="flex shrink-0 flex-wrap items-center gap-1.5 sm:justify-end">
                                {c.bindings.map((b) => (
                                  <span
                                    key={b.id}
                                    className="inline-flex items-center gap-1.5 rounded-full border border-border bg-muted/50 py-1 pr-1 pl-2.5 text-xs"
                                  >
                                    <span className="font-mono">{b.collector_type}</span>
                                    {b.schedule_minutes > 0 && (
                                      <span className="text-muted-foreground tabular">
                                        {b.schedule_minutes}m
                                      </span>
                                    )}
                                    <Button
                                      variant="ghost"
                                      size="icon"
                                      className="size-6 rounded-full"
                                      aria-label={`Run ${b.collector_type} now`}
                                      onClick={() => onRun(b.id)}
                                    >
                                      <Play size={11} weight="fill" />
                                    </Button>
                                  </span>
                                ))}
                                {!c.bindings.length && (
                                  byControl.has(c.id) ? (
                                    <Button variant="outline" size="sm" onClick={() => onSelect(c)}>
                                      <Sparkle size={14} />
                                      {byControl.get(c.id).length} suggested
                                    </Button>
                                  ) : (
                                    <span className="text-xs text-muted-foreground">
                                      suggested{" "}
                                      <span className="font-mono text-foreground">{c.suggested_collector}</span>
                                    </span>
                                  )
                                )}
                                <Button variant="outline" size="sm" onClick={() => onBind(c)}>
                                  <Plus size={14} />
                                  Collector
                                </Button>
                              </div>
                            </div>
                          </li>
                        );
                      })}
                    </ul>
                  </CollapsibleContent>
                </div>
              </Collapsible>
            );
          })}
        </div>
      )}

      {selected && (
        <ControlSheet
          control={selected}
          runs={runs}
          ready={ready[selected.id] || { status: "uncovered" }}
          suggestions={byControl.get(selected.id) || []}
          onBindSuggestion={bindSuggestion}
          onClose={() => onSelect(null)}
          onRun={onRun}
          onBind={onBind}
        />
      )}
    </>
  );
}

/* ---------- drill-down slide-over ---------- */
function ControlSheet({ control, runs, ready, suggestions, onBindSuggestion, onClose, onRun, onBind }) {
  const [previewEvidence, setPreviewEvidence] = useState(null);
  const bindingIds = new Set(control.bindings.map((b) => b.id));
  const history = runs.filter((r) => bindingIds.has(r.binding_id));
  const latest = history[0];

  return (
    <>
      <Sheet open onOpenChange={(o) => !o && onClose()}>
      <SheetContent className="w-full gap-0 overflow-y-auto sm:max-w-xl">
        <SheetHeader className="border-b border-border">
          <span className="font-mono text-xs text-muted-foreground">{control.code}</span>
          <SheetTitle className="text-lg leading-snug">{control.name}</SheetTitle>
          <SheetDescription className="sr-only">
            Details, collectors and run history for {control.code}.
          </SheetDescription>
          <div className="pt-1">
            <StatusBadge status={ready.status} />
          </div>
        </SheetHeader>

        <div className="space-y-6 px-4 pb-8">
          <section>
            <h3 className="mb-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">
              Description
            </h3>
            <p className="text-sm text-pretty">{control.description || "—"}</p>
          </section>

          {latest?.assessment && (
            <section>
              <h3 className="mb-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">
                Latest assessment
              </h3>
              <div
                className={cn(
                  "rounded-lg border p-3.5",
                  latest.assessment.satisfied
                    ? "border-status-satisfied/30 bg-status-satisfied-bg"
                    : "border-status-gap/30 bg-status-gap-bg"
                )}
              >
                <div className="flex items-center justify-between gap-3">
                  <span className="text-sm font-medium">
                    {latest.assessment.satisfied ? "Satisfies control" : "Gap found"}
                  </span>
                  <span className="text-xs text-muted-foreground tabular">
                    {Math.round(latest.assessment.confidence * 100)}% confidence
                  </span>
                </div>
                <p className="mt-1.5 text-sm text-pretty">{latest.assessment.summary}</p>
                {latest.assessment.gaps && (
                  <p className="mt-2 text-sm text-muted-foreground">
                    <span className="font-medium text-foreground">Gaps:</span> {latest.assessment.gaps}
                  </p>
                )}
              </div>
            </section>
          )}

          <section>
            <h3 className="mb-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">
              Collectors
            </h3>
            {control.bindings.length ? (
              <div className="flex flex-wrap gap-1.5">
                {control.bindings.map((b) => (
                  <span
                    key={b.id}
                    className="inline-flex items-center gap-1.5 rounded-full border border-border bg-muted/50 py-1 pr-1 pl-2.5 text-xs"
                  >
                    <span className="font-mono">{b.collector_type}</span>
                    {b.schedule_minutes > 0 && (
                      <span className="text-muted-foreground tabular">{b.schedule_minutes}m</span>
                    )}
                    <Button
                      variant="ghost"
                      size="icon"
                      className="size-6 rounded-full"
                      aria-label={`Run ${b.collector_type} now`}
                      onClick={() => onRun(b.id)}
                    >
                      <Play size={11} weight="fill" />
                    </Button>
                  </span>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">
                No collector mapped yet. Suggested:{" "}
                <span className="font-mono text-foreground">{control.suggested_collector}</span>
              </p>
            )}
            <Button variant="outline" size="sm" className="mt-3" onClick={() => onBind(control)}>
              <Plus size={14} />
              Add collector
            </Button>
          </section>

          {suggestions.length > 0 && (
            <section>
              <h3 className="mb-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">
                Suggested evidence ({suggestions.length})
              </h3>
              <ul className="space-y-2">
                {suggestions.map((s) => (
                  <li key={s.id} className="rounded-lg border border-border p-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="truncate font-mono text-sm" title={s.source_name}>
                          {s.source_name}
                        </div>
                        {/* The reason names the matched signals, so the suggestion can be
                            checked rather than taken on faith. */}
                        <div className="mt-0.5 text-xs text-pretty text-muted-foreground">
                          {s.reason}
                        </div>
                        <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
                          <span className="rounded-full bg-muted px-2 py-0.5 text-[11px] font-medium">
                            {matchStrength(s.score)}
                          </span>
                          <span className="rounded bg-muted px-1.5 py-0.5 font-mono text-[11px] text-muted-foreground">
                            {s.surface}
                          </span>
                          {s.signals?.age_days != null && (
                            <span className="text-[11px] text-muted-foreground">
                              {s.signals.age_days}d old
                            </span>
                          )}
                        </div>
                      </div>
                      <Button variant="outline" size="sm" onClick={() => onBindSuggestion(s)}>
                        Bind
                      </Button>
                    </div>
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section>
            <h3 className="mb-2 text-xs font-medium tracking-wide text-muted-foreground uppercase">
              Run history ({history.length})
            </h3>
            {history.length ? (
              <ul className="space-y-2">
                {history.map((r) => (
                  <li key={r.id} className="rounded-lg border border-border p-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="font-mono text-xs text-muted-foreground">
                        RUN-{String(r.id).padStart(4, "0")}
                      </span>
                      <StatusBadge
                        size="sm"
                        status={r.status === "success" ? "collected" : r.status === "error" ? "failed" : "pending"}
                      />
                      <span className="ml-auto text-xs text-muted-foreground">{r.message}</span>
                    </div>
                    {r.evidence.length > 0 && (
                      <ul className="mt-2 space-y-1 border-t border-dashed border-border pt-2">
                        {r.evidence.map((e) => (
                          <li
                            key={e.id}
                            className="flex items-center justify-between gap-2 rounded px-1.5 py-1 text-sm transition-colors hover:bg-muted/50 group"
                          >
                            <button
                              type="button"
                              onClick={() => setPreviewEvidence(e)}
                              className="flex items-center gap-2 min-w-0 flex-1 text-left transition-colors hover:text-primary font-medium"
                            >
                              <span className="min-w-0 truncate">{e.filename}</span>
                              <span className="font-mono text-xs text-muted-foreground">
                                {e.sha256.slice(0, 16)}…
                              </span>
                            </button>
                            <div className="flex items-center gap-1 shrink-0">
                              <button
                                type="button"
                                onClick={() => setPreviewEvidence(e)}
                                className="p-1 rounded text-muted-foreground hover:text-primary transition-colors"
                                title={`Preview ${e.filename}`}
                                aria-label={`Preview ${e.filename}`}
                              >
                                <Eye size={13} />
                              </button>
                              <a
                                href={downloadUrl(e.id)}
                                target="_blank"
                                rel="noreferrer"
                                download={e.filename}
                                className="p-1 rounded text-muted-foreground hover:text-foreground transition-colors"
                                title={`Download ${e.filename}`}
                                aria-label={`Download ${e.filename}`}
                              >
                                <DownloadSimple size={13} />
                              </a>
                            </div>
                          </li>
                        ))}
                      </ul>
                    )}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="text-sm text-muted-foreground">No runs yet.</p>
            )}
          </section>
        </div>
      </SheetContent>
    </Sheet>

    {previewEvidence && (
      <EvidencePreviewModal
        evidence={previewEvidence}
        onClose={() => setPreviewEvidence(null)}
      />
    )}
  </>
  );
}

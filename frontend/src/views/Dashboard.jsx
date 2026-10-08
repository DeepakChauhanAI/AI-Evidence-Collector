import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Progress } from "@/components/ui/progress";
import StatusBadge from "@/components/status-badge";
import { groupControls } from "@/lib/readiness";
import { ArrowClockwise, ArrowRight, ShieldCheck, Plugs, HourglassMedium } from "@phosphor-icons/react";

const READY = ["satisfied", "collected"];
// Most urgent first — a failed run matters more than a control never mapped.
const SEVERITY = { failed: 0, gap: 1, stale: 2, uncovered: 3, pending: 4 };
// The dashboard summarises; the Controls view is where you work through the list.
const SHOW = 6;

/* Runs per day for the last 30 days. The API returns runs newest-first and
   carries started_at, so this needs no backend change. */
function Trend({ runs }) {
  const DAYS = 30;
  const dayKey = (d) => d.toISOString().slice(0, 10);
  const counts = new Map();

  for (const r of runs) {
    const k = dayKey(new Date(r.started_at + "Z"));
    counts.set(k, (counts.get(k) ?? 0) + 1);
  }

  const today = new Date();
  const series = Array.from({ length: DAYS }, (_, i) => {
    const d = new Date(Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate() - (DAYS - 1 - i)));
    const k = dayKey(d);
    return { date: k, count: counts.get(k) ?? 0 };
  });

  const max = Math.max(1, ...series.map((s) => s.count));
  const total = series.reduce((a, s) => a + s.count, 0);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm">Collections, last 30 days</CardTitle>
      </CardHeader>
      <CardContent>
        {total === 0 ? (
          <p className="text-sm text-muted-foreground">No collections in this window.</p>
        ) : (
          <>
            <div className="flex h-20 items-end gap-[3px]" role="img"
                 aria-label={`${total} collections across the last 30 days`}>
              {series.map((s) => (
                <div
                  key={s.date}
                  title={`${s.date}: ${s.count} run${s.count === 1 ? "" : "s"}`}
                  className="flex-1 rounded-t-[3px] bg-primary/85 transition-colors hover:bg-primary"
                  style={{ height: `${Math.max(s.count === 0 ? 2 : 12, (s.count / max) * 100)}%` }}
                />
              ))}
            </div>
            <div className="mt-2 flex justify-between text-xs text-muted-foreground">
              <span>30 days ago</span>
              <span className="tabular">{total} runs</span>
              <span>today</span>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}

function StatTile({ icon: Icon, tone, value, label, sub }) {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-border bg-card px-4 py-3.5">
      <span className={`mt-0.5 ${tone}`}>
        <Icon size={18} weight="fill" aria-hidden />
      </span>
      <div className="min-w-0">
        <div className="text-xl font-semibold tracking-tight">{value}</div>
        <div className="text-xs font-medium text-foreground">{label}</div>
        {sub && <div className="mt-0.5 text-xs text-muted-foreground">{sub}</div>}
      </div>
    </div>
  );
}

export default function Dashboard({ controls, runs, ready, tally, onRecollect, staleIds, onSelect, onNavigate }) {
  const total = controls.length;
  const readyCount = tally.satisfied + tally.collected;
  const pct = total ? Math.round((readyCount / total) * 100) : 0;
  const notReady = total - readyCount;
  const groups = groupControls(controls);

  // Everything that isn't satisfied or collected needs attention — including
  // controls with no collector at all. Omitting "uncovered" here made the
  // dashboard claim "nothing needs attention" at 0% readiness.
  const attention = controls
    .filter((c) => !READY.includes((ready[c.id] || {}).status))
    .sort((a, b) => {
      const sa = SEVERITY[(ready[a.id] || {}).status] ?? 9;
      const sb = SEVERITY[(ready[b.id] || {}).status] ?? 9;
      return sa - sb || a.code.localeCompare(b.code, undefined, { numeric: true });
    });

  const recent = runs.slice(0, 5);

  return (
    <div className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-1">
          <CardContent className="pt-6">
            <div className="text-xs font-medium tracking-wide text-muted-foreground uppercase">
              Audit readiness
            </div>
            <div className="mt-1 flex items-baseline gap-2">
              <span className="text-4xl font-semibold tracking-tight">{pct}%</span>
              <span className="text-sm text-muted-foreground">
                {readyCount} of {total} controls
              </span>
            </div>
            <Progress value={pct} className="mt-4" />
            <p className="mt-3 text-sm text-pretty text-muted-foreground">
              {notReady === 0
                ? "Every control is satisfied with fresh evidence."
                : `${notReady} control${notReady === 1 ? "" : "s"} still need evidence before this period closes.`}
            </p>
          </CardContent>
        </Card>

        <div className="grid gap-4 sm:grid-cols-2 lg:col-span-2">
          <StatTile icon={ShieldCheck} tone="text-status-satisfied" value={readyCount}
                    label="Satisfied" sub="evidence fresh and passing" />
          <StatTile icon={ArrowRight} tone="text-status-gap" value={tally.gap + tally.failed}
                    label="Gaps & failures" sub="collected but not accepted" />
          <StatTile icon={HourglassMedium} tone="text-status-stale" value={tally.stale}
                    label="Stale" sub="evidence aged out" />
          <StatTile icon={Plugs} tone="text-status-uncovered" value={tally.uncovered + tally.pending}
                    label="Not covered" sub="no collector mapped" />
        </div>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">
            Needs attention
            <span className="ml-2 font-normal text-muted-foreground tabular">({attention.length})</span>
          </CardTitle>
          {staleIds.length > 0 && (
            <Button variant="outline" size="sm" onClick={() => onRecollect(staleIds)}>
              <ArrowClockwise size={16} />
              Recollect stale ({staleIds.length})
            </Button>
          )}
        </CardHeader>
        <CardContent>
          {attention.length === 0 ? (
            <p className="py-2 text-sm text-muted-foreground">
              Nothing needs attention. Every control is satisfied and fresh.
            </p>
          ) : (
            <>
              <ul className="-my-1 divide-y divide-border">
                {attention.slice(0, SHOW).map((c) => (
                  <li key={c.id}>
                    <button
                      type="button"
                      onClick={() => onSelect(c)}
                      className="flex w-full items-center gap-3 px-1 py-2.5 text-left transition-colors hover:bg-muted/50"
                    >
                      <span className="w-16 shrink-0 font-mono text-xs text-muted-foreground">
                        {c.code}
                      </span>
                      <span className="min-w-0 flex-1 truncate text-sm">{c.name}</span>
                      <StatusBadge status={(ready[c.id] || {}).status} size="sm" />
                    </button>
                  </li>
                ))}
              </ul>
              {attention.length > SHOW && (
                <button
                  type="button"
                  onClick={() => onNavigate?.("controls")}
                  className="mt-3 inline-flex items-center gap-1.5 text-sm font-medium text-primary hover:underline"
                >
                  View all {attention.length} in Controls
                  <ArrowRight size={14} />
                </button>
              )}
            </>
          )}
        </CardContent>
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle className="text-sm">Coverage by category</CardTitle>
          </CardHeader>
          <CardContent className="space-y-4">
            {groups.map((g) => {
              const rdy = g.controls.filter((c) => READY.includes((ready[c.id] || {}).status)).length;
              const gpct = Math.round((rdy / g.controls.length) * 100);
              return (
                <div key={g.key}>
                  <div className="mb-1.5 flex items-baseline justify-between gap-3">
                    <span className="truncate text-sm">
                      <span className="font-mono text-xs text-muted-foreground">{g.key}</span>{" "}
                      {g.name}
                    </span>
                    <span className="shrink-0 text-xs text-muted-foreground tabular">
                      {rdy}/{g.controls.length}
                    </span>
                  </div>
                  <Progress value={gpct} className="h-1.5" />
                </div>
              );
            })}
          </CardContent>
        </Card>

        <div className="space-y-4">
          <Trend runs={runs} />
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Recent activity</CardTitle>
            </CardHeader>
            <CardContent>
              {recent.length ? (
                <ul className="-my-1 divide-y divide-border">
                  {recent.map((r) => (
                    <li key={r.id} className="flex items-center gap-3 py-2 text-sm">
                      <span className="font-mono text-xs text-muted-foreground">
                        RUN-{String(r.id).padStart(4, "0")}
                      </span>
                      <span className="min-w-0 flex-1 truncate text-muted-foreground">{r.message}</span>
                      <StatusBadge
                        size="sm"
                        status={r.status === "success" ? "collected" : r.status === "error" ? "failed" : "pending"}
                      />
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="py-2 text-sm text-muted-foreground">No runs yet.</p>
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

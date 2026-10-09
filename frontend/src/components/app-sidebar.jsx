import {
  Gauge,
  ListChecks,
  FolderOpen,
  Pulse,
  PlugsConnected,
  Crosshair,
  CaretLeft,
  CaretRight,
} from "@phosphor-icons/react";
import { cn } from "@/lib/utils";

export const NAV = [
  { key: "dashboard", label: "Dashboard", icon: Gauge },
  { key: "controls", label: "Controls", icon: ListChecks },
  { key: "discovery", label: "Discovery", icon: Crosshair },
  { key: "evidence", label: "Evidence", icon: FolderOpen },
  { key: "activity", label: "Activity", icon: Pulse },
  { key: "sources", label: "Sources", icon: PlugsConnected },
];

/* One curve and duration for every part of the collapse, so the edge, the
   labels and the brand all move as a single gesture rather than three
   animations that happen to overlap. */
const EASE = "duration-200 ease-[cubic-bezier(0.32,0.72,0,1)]";

/* Labels are clipped, never unmounted. Rendering them conditionally made the
   text pop out instantly while the rail was still mid-animation — that
   mismatch is what made the transition feel broken.
   margin-left is animated alongside max-width so the gap to the icon closes
   smoothly too; that is what lets the button keep justify-center in both
   states without the icon ever jumping. */
const CLIP = cn(
  "overflow-hidden whitespace-nowrap transition-[max-width,opacity,margin-left]",
  EASE
);

/* grid-cols-1 + place-items-center: both lockups sit in the same cell, centred.
   As the rail narrows the wide lockup is clipped symmetrically from both sides
   rather than shrinking, so it fades out in place. Fixed height means the
   collapse changes only width — nothing below the header shifts vertically
   while the transition runs.

   The expanded lockup is a vector, traced from the 2104x813 footer lockup on
   panaceainfosec.com rather than the 240x94 header file. That is ~9x the
   resolution, and it is the difference between a clean trace and a rough one.
   Region colours were painted flat before tracing, so vtracer only had to
   recover geometry. */
export function Brand({ collapsed = false }) {
  return (
    <div className="grid h-[4.5rem] grid-cols-1 place-items-center overflow-hidden">
      <div
        className={cn(
          "col-start-1 row-start-1 flex w-[8.875rem] flex-col items-center gap-1.5 transition-opacity",
          EASE,
          collapsed ? "pointer-events-none opacity-0" : "opacity-100"
        )}
      >
        <img
          src="/panacea_logo.svg"
          alt="Panacea InfoSec"
          className="h-auto w-full"
        />
        <span className="w-full text-center text-[12.5px] font-semibold tracking-[0.04em] text-muted-foreground whitespace-nowrap">
          AI Evidence Collector
        </span>
      </div>
      {/* Decorative: the lockup above still carries the accessible name while
          faded out, so this must not repeat it. */}
      <img
        src="/panacea_icon.svg"
        alt=""
        aria-hidden
        className={cn(
          // h-8 w-auto, not size-8: the mark is taller than it is wide (0.817),
          // and size-* would force both axes and squash it.
          "col-start-1 row-start-1 h-8 w-auto transition-opacity",
          EASE,
          collapsed ? "opacity-100" : "opacity-0"
        )}
      />
    </div>
  );
}

/** Nav list — shared by the desktop rail and the mobile sheet so they can't drift.
 *  The mobile sheet always passes collapsed={false}. */
export function NavItems({ view, onNavigate, counts, collapsed = false }) {
  return (
    <nav aria-label="Sections" className="flex flex-col gap-0.5">
      {NAV.map(({ key, label, icon: Icon }) => {
        const active = view === key;
        return (
          <button
            key={key}
            type="button"
            onClick={() => onNavigate(key)}
            aria-current={active ? "page" : undefined}
            title={collapsed ? label : undefined}
            className={cn(
              // justify-center with no gap: while the label wrapper still has
              // width it absorbs all the free space so centring does nothing,
              // and as it shrinks the icon eases to the middle on its own.
              "flex items-center justify-center overflow-hidden rounded-md px-2.5 py-2 text-left text-sm font-medium transition-colors",
              "focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none",
              active
                ? "bg-sidebar-accent text-sidebar-accent-foreground"
                : "text-muted-foreground hover:bg-sidebar-accent/60 hover:text-foreground"
            )}
          >
            <Icon size={16} weight={active ? "fill" : "regular"} className="shrink-0" aria-hidden />
            <span
              className={cn(
                "flex min-w-0 flex-1 items-center justify-between gap-2",
                CLIP,
                collapsed ? "ml-0 max-w-0 opacity-0" : "ml-2.5 max-w-full opacity-100"
              )}
            >
              <span className="truncate">{label}</span>
              {counts[key] != null && (
                <span
                  className={cn(
                    "tabular rounded-full px-2 py-0.5 text-[11px] font-semibold transition-colors",
                    active
                      ? "bg-primary/10 text-primary"
                      : "bg-muted text-muted-foreground"
                  )}
                >
                  {counts[key]}
                </span>
              )}
            </span>
          </button>
        );
      })}
    </nav>
  );
}

export default function AppSidebar({ view, onNavigate, counts, collapsed, onToggle }) {
  return (
    <aside
      className={cn(
        "hidden shrink-0 border-r border-sidebar-border bg-sidebar",
        "lg:sticky lg:top-0 lg:flex lg:h-dvh lg:flex-col",
        "transition-[width]",
        EASE,
        collapsed ? "w-16" : "w-52"
      )}
    >
      <div className="overflow-hidden px-3 py-4">
        <Brand collapsed={collapsed} />
      </div>

      <div className="flex-1 overflow-y-auto px-3">
        <NavItems view={view} onNavigate={onNavigate} counts={counts} collapsed={collapsed} />
      </div>

      {/* No rule above this block and no label text — a compact icon button, so
          the hover target is the size of the glyph rather than spanning the
          rail. Right-aligned in both states: the chevron then slides left as
          the rail narrows instead of jumping between two positions. */}
      <div className="flex justify-end px-3 py-2">
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={!collapsed}
          aria-label={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
          className={cn(
            "grid size-7 shrink-0 place-items-center rounded-md text-muted-foreground transition-colors",
            "hover:bg-sidebar-accent/60 hover:text-foreground",
            "focus-visible:ring-[3px] focus-visible:ring-ring/50 focus-visible:outline-none"
          )}
        >
          {collapsed ? (
            <CaretRight size={14} aria-hidden />
          ) : (
            <CaretLeft size={14} aria-hidden />
          )}
        </button>
      </div>
    </aside>
  );
}

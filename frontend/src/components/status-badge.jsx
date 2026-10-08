import { cva } from "class-variance-authority";
import {
  SealCheck,
  CheckCircle,
  Warning,
  HourglassMedium,
  Circle,
  XCircle,
  Plugs,
} from "@phosphor-icons/react";
import { cn } from "@/lib/utils";
import { STATUS_LABEL } from "@/lib/readiness";

/**
 * The one place a control's readiness state maps to colour + icon + wording.
 * Previously these leaked as raw hex across three stylesheets; anything showing
 * status must route through here so the vocabulary can't drift.
 *
 * The status hue paints the ICON and the tint, never the label. Colouring the
 * text with the status hue put "stale" at 2.26:1 on its own tint — and the hue
 * cannot simply be darkened, because that collapses it into "gap" under
 * protanopia (ΔE 0.1). Ink stays ink; the coloured mark carries identity.
 */
const VARIANTS = {
  satisfied: { icon: SealCheck, weight: "fill", color: "text-status-satisfied" },
  collected: { icon: CheckCircle, weight: "fill", color: "text-status-collected" },
  gap: { icon: Warning, weight: "fill", color: "text-status-gap" },
  stale: { icon: HourglassMedium, weight: "fill", color: "text-status-stale" },
  pending: { icon: Circle, weight: "regular", color: "text-status-pending" },
  failed: { icon: XCircle, weight: "fill", color: "text-status-failed" },
  uncovered: { icon: Plugs, weight: "regular", color: "text-status-uncovered" },
};

// Classes are written out in full, NOT built from a template. Tailwind v4 scans
// source for literal strings, so `bg-status-${s}-bg` would emit no CSS at all
// and fail silently — do not "DRY" these back into a generator.
const statusBadge = cva(
  "inline-flex shrink-0 items-center gap-1.5 rounded-full font-medium whitespace-nowrap text-foreground",
  {
    variants: {
      status: {
        satisfied: "bg-status-satisfied-bg",
        collected: "bg-status-collected-bg",
        gap: "bg-status-gap-bg",
        stale: "bg-status-stale-bg",
        pending: "bg-status-pending-bg",
        failed: "bg-status-failed-bg",
        uncovered: "bg-status-uncovered-bg",
      },
      size: {
        sm: "px-2 py-0.5 text-[11px]",
        default: "px-2.5 py-1 text-xs",
      },
    },
    defaultVariants: { status: "uncovered", size: "default" },
  }
);

export default function StatusBadge({ status = "uncovered", size, className, showIcon = true }) {
  const variant = VARIANTS[status] ?? VARIANTS.uncovered;
  const Icon = variant.icon;

  return (
    <span className={cn(statusBadge({ status, size }), className)}>
      {showIcon && (
        <Icon size={12} weight={variant.weight} className={variant.color} aria-hidden />
      )}
      {STATUS_LABEL[status] ?? status}
    </span>
  );
}

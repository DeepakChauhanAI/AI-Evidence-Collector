import {
  CheckCircle,
  Info,
  CircleNotch,
  WarningOctagon,
  Warning,
} from "@phosphor-icons/react"
import { Toaster as Sonner } from "sonner";

// Light-first app with no theme provider — pin the toaster to light rather than
// pulling in next-themes for a value that never changes.
const Toaster = ({ ...props }) => (
  <Sonner
    theme="light"
    className="toaster group"
    icons={{
      success: <CheckCircle className="size-4" weight="fill" />,
      info: <Info className="size-4" weight="fill" />,
      warning: <Warning className="size-4" weight="fill" />,
      error: <WarningOctagon className="size-4" weight="fill" />,
      loading: <CircleNotch className="size-4 animate-spin" />,
    }}
    style={{
      "--normal-bg": "var(--popover)",
      "--normal-text": "var(--popover-foreground)",
      "--normal-border": "var(--border)",
      "--border-radius": "var(--radius)",
    }}
    {...props}
  />
);

export { Toaster }

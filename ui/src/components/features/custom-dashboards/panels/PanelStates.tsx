import type { ReactNode } from "react";

import { CircleAlert, Info, TriangleAlert } from "lucide-react";

const TONES = {
  info: { icon: Info, className: "text-base-content/60" },
  warning: { icon: TriangleAlert, className: "text-warning" },
  error: { icon: CircleAlert, className: "text-error" },
} as const;

/** Centered one-line state inside a panel body: empty, misconfigured or failed. */
export function PanelMessage({
  children,
  tone = "info",
}: {
  children: ReactNode;
  tone?: keyof typeof TONES;
}) {
  const { icon: Icon, className } = TONES[tone];
  return (
    <div
      role={tone === "error" ? "alert" : undefined}
      className="flex h-full min-h-16 items-center justify-center gap-2 px-3 text-center text-sm text-base-content/70"
    >
      <Icon className={`h-4 w-4 shrink-0 ${className}`} aria-hidden="true" />
      <span className="min-w-0">{children}</span>
    </div>
  );
}

/** Loading placeholder that fills a panel body. */
export function PanelSkeleton() {
  return (
    <div className="flex h-full min-h-16 flex-col gap-2" aria-busy="true" aria-label="Loading">
      <div className="skeleton h-4 w-1/3" />
      <div className="skeleton min-h-0 flex-1" />
    </div>
  );
}

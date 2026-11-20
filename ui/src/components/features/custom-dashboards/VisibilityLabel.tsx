import { Lock, Users } from "lucide-react";

import type { CustomDashboardResponseVisibility } from "@/schemas";

/** Who can open a dashboard or script, as a line of meta text with its icon. */
export function VisibilityLabel({
  visibility,
  className = "",
}: {
  visibility: CustomDashboardResponseVisibility;
  className?: string;
}) {
  const shared = visibility === "project";
  const Icon = shared ? Users : Lock;
  return (
    <span className={`inline-flex items-center gap-1 ${className}`}>
      <Icon className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
      {shared ? "Shared with project" : "Private"}
    </span>
  );
}

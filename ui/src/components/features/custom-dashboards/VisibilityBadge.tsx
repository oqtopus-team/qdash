import { Lock, Users } from "lucide-react";

import type { CustomDashboardResponseVisibility } from "@/schemas";

export function VisibilityBadge({ visibility }: { visibility: CustomDashboardResponseVisibility }) {
  const shared = visibility === "project";
  const Icon = shared ? Users : Lock;
  return (
    <span className={`badge badge-sm gap-1 ${shared ? "badge-info badge-soft" : "badge-ghost"}`}>
      <Icon className="h-3 w-3" aria-hidden="true" />
      {shared ? "Shared with project" : "Private"}
    </span>
  );
}

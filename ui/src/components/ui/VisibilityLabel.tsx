import { Lock, Users } from "lucide-react";

/** Who can open a record: its owner only, or every member of the project. */
export type Visibility = "private" | "project";

/** Who can open a record, as a line of meta text with its icon. */
export function VisibilityLabel({
  visibility,
  privateLabel = "Private",
  projectLabel = "Shared with project",
  className = "",
}: {
  visibility: Visibility;
  privateLabel?: string;
  projectLabel?: string;
  className?: string;
}) {
  const shared = visibility === "project";
  const Icon = shared ? Users : Lock;
  return (
    <span className={`inline-flex items-center gap-1 ${className}`}>
      <Icon className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
      {shared ? projectLabel : privateLabel}
    </span>
  );
}

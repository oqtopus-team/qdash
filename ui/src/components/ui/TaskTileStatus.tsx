import { Clock, LoaderCircle, X } from "lucide-react";
import { twMerge } from "tailwind-merge";

type TaskTileStatusKind = "completed" | "failed" | "running" | "waiting";

function statusKind(status: string | undefined): TaskTileStatusKind {
  if (status === "completed" || status === "failed" || status === "running") return status;
  return "waiting";
}

const STATUS_STYLES: Record<TaskTileStatusKind, { fill: string; content: string }> = {
  completed: { fill: "bg-success", content: "text-success-content" },
  failed: { fill: "bg-error", content: "text-error-content" },
  // Running keeps the warning fill the grids have always used; the glyph tells it apart.
  running: { fill: "bg-warning", content: "text-warning-content" },
  waiting: { fill: "bg-warning", content: "text-warning-content" },
};

const STATUS_ICONS = {
  failed: X,
  running: LoaderCircle,
  waiting: Clock,
} as const;

/** Background fill for a status-colored chip tile. */
export function taskTileStatusFill(status: string | undefined): string {
  return STATUS_STYLES[statusKind(status)].fill;
}

/** Accessible name and tooltip text for a chip tile, e.g. "Qubit 12: failed (3 tasks)". */
export function taskTileLabel(
  entity: "Qubit" | "Coupling",
  id: string,
  status: string | undefined,
  taskCount = 1,
): string {
  const tasks = taskCount > 1 ? ` (${taskCount} tasks)` : "";
  return `${entity} ${id}: ${status || "unknown"}${tasks}`;
}

/**
 * Non-color cue for a tile's status. Completed tiles stay unmarked so a healthy chip reads
 * quietly; failed, running and waiting tiles carry a glyph. `variant="figure"` draws the
 * corner marker on a figure tile, where completed keeps its small dot.
 */
export function TaskTileStatusMark({
  status,
  variant,
  className,
}: {
  status: string | undefined;
  variant: "tile" | "figure";
  className?: string;
}) {
  const kind = statusKind(status);
  const styles = STATUS_STYLES[kind];

  if (kind === "completed") {
    if (variant === "tile") return null;
    return (
      <span
        aria-hidden="true"
        className={twMerge("h-2 w-2 rounded-full", styles.fill, className)}
      />
    );
  }

  const Icon = STATUS_ICONS[kind];
  if (variant === "tile") {
    return (
      <Icon
        aria-hidden="true"
        size={10}
        strokeWidth={3}
        className={twMerge(styles.content, className)}
      />
    );
  }
  return (
    <span
      aria-hidden="true"
      className={twMerge(
        "flex h-3.5 w-3.5 items-center justify-center rounded-full",
        styles.fill,
        styles.content,
        className,
      )}
    >
      <Icon size={9} strokeWidth={3} />
    </span>
  );
}

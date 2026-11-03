import { twMerge } from "tailwind-merge";

type QubitTileProps = {
  /** Qubit id such as "12" or coupling id such as "12-13", shown as stored. */
  qid: string;
  /** Task or result status; renders a status dot when given. */
  status?: string | null;
  className?: string;
};

function dotClass(status: string): string {
  switch (status) {
    case "completed":
      return "bg-success";
    case "failed":
      return "bg-error";
    case "running":
      return "bg-info";
    case "scheduled":
    case "pending":
      return "bg-warning";
    default:
      return "bg-base-content/30";
  }
}

/**
 * The qubit tile: a mono id in a small square-cornered box, the same shape as a cell in the chip
 * grid, so a target reads the same everywhere a qubit or coupling is referenced.
 */
export function QubitTile({ qid, status, className }: QubitTileProps) {
  return (
    <span
      className={twMerge(
        "inline-flex h-5 shrink-0 items-center gap-1.5 rounded border border-base-content/15 bg-base-200/60 px-1.5 font-mono text-xs tabular-nums text-base-content",
        className,
      )}
    >
      {status ? (
        <span
          className={twMerge("h-1.5 w-1.5 rounded-full", dotClass(status))}
          aria-hidden="true"
        />
      ) : null}
      {qid}
    </span>
  );
}

import type { FlowScheduleSummary } from "@/schemas";

type SortableSchedule = Pick<FlowScheduleSummary, "next_run" | "flow_name">;

/**
 * Sorts flow schedules by next run time ascending, without mutating the input.
 * Schedules with no next_run are sorted last; ties are broken by flow_name.
 */
export function sortSchedulesByNextRun<T extends SortableSchedule>(schedules: readonly T[]): T[] {
  return [...schedules].sort((a, b) => {
    const aTime = a.next_run ? new Date(a.next_run).getTime() : Number.MAX_SAFE_INTEGER;
    const bTime = b.next_run ? new Date(b.next_run).getTime() : Number.MAX_SAFE_INTEGER;
    if (aTime !== bTime) return aTime - bTime;
    return a.flow_name.localeCompare(b.flow_name);
  });
}

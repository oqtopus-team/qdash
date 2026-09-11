import type { ChipResponse } from "@/schemas";

type SortableChip = Pick<ChipResponse, "chip_id" | "installed_at" | "activity_status">;

export function sortChipsByDefaultPriority<T extends SortableChip>(chips: readonly T[]): T[] {
  return [...chips].sort((a, b) => {
    const statusA = a.activity_status === "inactive" ? 1 : 0;
    const statusB = b.activity_status === "inactive" ? 1 : 0;
    if (statusA !== statusB) return statusA - statusB;

    const dateA = a.installed_at ? new Date(a.installed_at).getTime() : 0;
    const dateB = b.installed_at ? new Date(b.installed_at).getTime() : 0;
    if (dateA !== dateB) return dateB - dateA;

    return a.chip_id.localeCompare(b.chip_id);
  });
}

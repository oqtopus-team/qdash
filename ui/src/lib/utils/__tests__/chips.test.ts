import { describe, expect, it } from "vitest";

import { sortChipsByDefaultPriority } from "@/lib/utils/chips";

describe("sortChipsByDefaultPriority", () => {
  it("places active chips first and then sorts by installed_at descending", () => {
    const chips = [
      {
        chip_id: "inactive-new",
        activity_status: "inactive",
        installed_at: "2026-06-01T00:00:00Z",
      },
      {
        chip_id: "active-old",
        activity_status: "active",
        installed_at: "2024-06-01T00:00:00Z",
      },
      {
        chip_id: "active-new",
        activity_status: "active",
        installed_at: "2025-06-01T00:00:00Z",
      },
    ] as const;

    expect(sortChipsByDefaultPriority(chips).map((chip) => chip.chip_id)).toEqual([
      "active-new",
      "active-old",
      "inactive-new",
    ]);
  });
});

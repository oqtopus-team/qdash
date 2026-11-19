"use client";

import { useMemo } from "react";

import { useGetChip, useListChips } from "@/client/chip/chip";
import { sortChipsByDefaultPriority } from "@/lib/utils/chips";

/** The chip a view falls back to: the most recently installed active one. */
export function useDefaultChipId(): string {
  const { data } = useListChips();
  return useMemo(
    () => sortChipsByDefaultPriority(data?.data?.chips ?? [])[0]?.chip_id ?? "",
    [data],
  );
}

/** Topology of a chip, falling back to the square lattice of its size. */
export function useChipTopologyId(chipId: string): string {
  const { data } = useGetChip(chipId, { query: { enabled: !!chipId } });
  return data?.data?.topology_id ?? `square-lattice-mux-${data?.data?.size ?? 64}`;
}

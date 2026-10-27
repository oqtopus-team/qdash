"use client";

import { useEffect, useMemo } from "react";

import type { ChipSystemInfo } from "@/schemas";

import { useListChipSystems } from "@/client/chip/chip";

/** Systems of a chip, with the selection validated against the list. */
export function useChipSystems(chipId: string, selectedSystemId: string | null) {
  const { data, isLoading } = useListChipSystems(chipId, {
    query: { enabled: Boolean(chipId), staleTime: 60_000 },
  });
  const systems = useMemo<ChipSystemInfo[]>(() => data?.data?.systems ?? [], [data]);
  const selectedSystem = useMemo(
    () => systems.find((system) => system.system_id === selectedSystemId) ?? null,
    [systems, selectedSystemId],
  );
  return { systems, selectedSystem, isLoading, hasChoice: systems.length > 1 };
}

interface SystemSelectorProps {
  chipId: string;
  selectedSystemId: string | null;
  onSelect: (systemId: string | null) => void;
  className?: string;
}

/**
 * Segmented control switching the page between the Systems of a chip.
 * Renders nothing while the chip has one System; a selection that no longer
 * exists on the chip is cleared.
 */
export function SystemSelector({
  chipId,
  selectedSystemId,
  onSelect,
  className = "",
}: SystemSelectorProps) {
  const { systems, selectedSystem, isLoading, hasChoice } = useChipSystems(
    chipId,
    selectedSystemId,
  );

  useEffect(() => {
    if (!isLoading && chipId && selectedSystemId && !selectedSystem) {
      onSelect(null);
    }
  }, [chipId, isLoading, onSelect, selectedSystem, selectedSystemId]);

  if (!hasChoice) return null;

  return (
    <div
      className={`join overflow-hidden rounded-lg ${className}`}
      role="group"
      aria-label="System"
    >
      <button
        type="button"
        aria-pressed={selectedSystem === null}
        className={`join-item btn btn-sm ${selectedSystem === null ? "btn-primary" : ""}`}
        onClick={() => onSelect(null)}
        title="Every System of the chip"
      >
        All Systems
      </button>
      {systems.map((system) => (
        <button
          key={system.system_id}
          type="button"
          aria-pressed={selectedSystem?.system_id === system.system_id}
          className={`join-item btn btn-sm gap-1 ${
            selectedSystem?.system_id === system.system_id ? "btn-primary" : ""
          }`}
          onClick={() => onSelect(system.system_id)}
          aria-label={`${system.system_id} (${system.backend})`}
          title={`MUX ${(system.mux_ids ?? []).join(", ") || "none"}`}
        >
          {system.system_id}
          <span className="badge badge-xs badge-ghost">{system.backend}</span>
        </button>
      ))}
    </div>
  );
}

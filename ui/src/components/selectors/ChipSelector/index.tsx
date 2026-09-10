"use client";

import { useMemo } from "react";

import Select from "react-select";

import type { SingleValue } from "react-select";

import { useListChips } from "@/client/chip/chip";
import { useSelectStyles } from "@/hooks/useSelectStyles";
import { sortChipsByDefaultPriority } from "@/lib/utils/chips";
import { formatDate } from "@/lib/utils/datetime";

interface ChipOption {
  value: string;
  label: string;
  installed_at?: string | null;
  activity_status: "active" | "inactive";
}

interface ChipSelectorProps {
  selectedChip: string;
  onChipSelect: (chipId: string) => void;
}

const PLACEHOLDER = "Select a chip";

/**
 * Component for selecting a chip from available chips
 */
export function ChipSelector({ selectedChip, onChipSelect }: ChipSelectorProps) {
  // Use lightweight endpoint (~0.2KB vs ~300KB with embedded data)
  const { data: chips, isLoading, isError } = useListChips();

  const sortedOptions = useMemo(() => {
    if (!chips?.data?.chips) return [];

    return sortChipsByDefaultPriority(chips.data.chips).map((chip) => {
      const activityStatus = chip.activity_status ?? "active";
      const installedAt = chip.installed_at ? `(${formatDate(chip.installed_at)})` : "";
      const inactiveLabel = activityStatus === "inactive" ? "Inactive" : "";

      return {
        value: chip.chip_id,
        label: [chip.chip_id, installedAt, inactiveLabel].filter(Boolean).join(" "),
        installed_at: chip.installed_at,
        activity_status: activityStatus,
      };
    });
  }, [chips]);

  const styles = useSelectStyles<ChipOption>();

  if (isLoading) {
    return (
      <div className="w-full animate-pulse">
        <div className="h-[38px] bg-base-300 rounded"></div>
      </div>
    );
  }

  if (isError) {
    return <div className="text-error text-sm">Failed to load chips</div>;
  }

  const handleChange = (option: SingleValue<ChipOption>) => {
    onChipSelect(option ? option.value : "");
  };

  return (
    <Select<ChipOption>
      options={sortedOptions}
      value={sortedOptions.find((option) => option.value === selectedChip) ?? null}
      onChange={handleChange}
      placeholder={PLACEHOLDER}
      className="text-base-content"
      styles={styles}
    />
  );
}

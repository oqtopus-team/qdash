"use client";

import { useEffect, useMemo } from "react";
import { useListChips } from "@/client/chip/chip";
import Select, { SingleValue } from "react-select";

interface ChipOption {
  value: string;
  label: string;
  installed_at?: string;
}

interface ChipSelectorProps {
  selectedChip: string;
  onChipSelect: (chipId: string) => void;
}

export function ChipSelector({
  selectedChip,
  onChipSelect,
}: ChipSelectorProps) {
  const { data: chips, isLoading, isError } = useListChips();

  const sortedOptions = useMemo(() => {
    if (!chips?.data) return [];

    return [...chips.data]
      .sort((a, b) => {
        const dateA = a.installed_at ? new Date(a.installed_at).getTime() : 0;
        const dateB = b.installed_at ? new Date(b.installed_at).getTime() : 0;
        return dateB - dateA;
      })
      .map((chip) => ({
        value: chip.chip_id,
        label: `${chip.chip_id} ${
          chip.installed_at
            ? `(${new Date(chip.installed_at).toLocaleDateString()})`
            : ""
        }`,
        installed_at: chip.installed_at,
      }));
  }, [chips]);

  useEffect(() => {
    if (
      sortedOptions.length > 0 &&
      (!selectedChip || selectedChip === "" || selectedChip === "SAMPLE")
    ) {
      // Set the most recently installed chip as default
      onChipSelect(sortedOptions[0].value);
    }
  }, [sortedOptions]); // Only run when options are loaded

  if (isLoading) {
    return (
      <div className="w-full max-w-xs animate-pulse">
        <div className="h-10 bg-base-300 rounded-lg"></div>
      </div>
    );
  }

  if (isError) {
    return (
      <div className="alert alert-error max-w-xs">
        <span>Failed to load chips</span>
      </div>
    );
  }

  const handleChange = (option: SingleValue<ChipOption>) => {
    if (option) {
      onChipSelect(option.value);
    }
  };

  return (
    <div className="w-full max-w-xs">
      <label className="label">
        <span className="label-text font-medium">Select Chip</span>
      </label>
      <Select<ChipOption>
        options={sortedOptions}
        value={sortedOptions.find((option) => option.value === selectedChip)}
        onChange={handleChange}
        placeholder="Select a chip"
        className="text-base-content"
      />
    </div>
  );
}

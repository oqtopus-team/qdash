"use client";

import { useMemo } from "react";

import Select from "react-select";

import type { SingleValue } from "react-select";

import { useListChips } from "@/client/chip/chip";
import { useSelectStyles } from "@/hooks/useSelectStyles";

interface ChipOption {
  value: string;
  label: string;
  installed_at?: string | null;
}

interface ChipSelectorProps {
  selectedChip: string;
  onChipSelect: (chipId: string) => void;
}

const PLACEHOLDER = "Select a chip";

export function ChipSelector({
  selectedChip,
  onChipSelect,
}: ChipSelectorProps) {
  // Use lightweight endpoint (~0.2KB vs ~300KB with embedded data)
  const { data: chips, isLoading, isError } = useListChips();

  const sortedOptions = useMemo(() => {
    if (!chips?.data?.chips) return [];

    return [...chips.data.chips]
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

  const { minWidth, styles } = useSelectStyles<ChipOption>({
    labels: sortedOptions.map((opt) => opt.label),
    placeholder: PLACEHOLDER,
  });

  if (isLoading) {
    return (
      <div className="animate-pulse" style={{ minWidth }}>
        <div className="h-[38px] bg-base-300 rounded"></div>
      </div>
    );
  }

  if (isError) {
    return <div className="text-error text-sm">Failed to load chips</div>;
  }

  const handleChange = (option: SingleValue<ChipOption>) => {
    if (option) {
      onChipSelect(option.value);
    }
  };

  return (
    <Select<ChipOption>
      options={sortedOptions}
      value={sortedOptions.find((option) => option.value === selectedChip)}
      onChange={handleChange}
      placeholder={PLACEHOLDER}
      className="text-base-content"
      styles={styles}
    />
  );
}

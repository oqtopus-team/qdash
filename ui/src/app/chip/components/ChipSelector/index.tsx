"use client";

import { useListChips } from "@/client/chip/chip";

interface ChipSelectorProps {
  selectedChip: string;
  onChipSelect: (chipId: string) => void;
}

export function ChipSelector({
  selectedChip,
  onChipSelect,
}: ChipSelectorProps) {
  const { data: chips, isLoading, isError } = useListChips();

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

  return (
    <div className="form-control w-full max-w-xs">
      <label className="label">
        <span className="label-text font-medium">Select Chip</span>
      </label>
      <select
        className="select select-bordered rounded-lg"
        value={selectedChip}
        onChange={(e) => onChipSelect(e.target.value)}
      >
        <option value="">Select a chip</option>
        {chips?.data.map((chip) => (
          <option key={chip.chip_id} value={chip.chip_id}>
            {chip.chip_id}
          </option>
        ))}
      </select>
    </div>
  );
}

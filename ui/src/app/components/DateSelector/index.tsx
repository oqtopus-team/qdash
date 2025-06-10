"use client";

import { useFetchChipDates } from "@/client/chip/chip";

interface DateSelectorProps {
  chipId: string;
  selectedDate: string;
  onDateSelect: (date: string) => void;
  disabled?: boolean;
}

export function DateSelector({
  chipId,
  selectedDate,
  onDateSelect,
  disabled = false,
}: DateSelectorProps) {
  const { data: datesResponse, isLoading } = useFetchChipDates(chipId, {
    query: {
      enabled: !disabled && !!chipId,
    },
  });

  console.log("DateSelector:", { chipId, disabled, datesResponse });

  const dates = ["latest"];
  if (datesResponse?.data && Array.isArray(datesResponse.data)) {
    dates.push(...datesResponse.data);
  }

  return (
    <select
      className="select select-bordered w-full max-w-xs"
      value={selectedDate}
      onChange={(e) => onDateSelect(e.target.value)}
      disabled={disabled || isLoading}
    >
      {dates.map((date) => (
        <option key={date} value={date}>
          {date === "latest" ? "Latest" : date}
        </option>
      ))}
    </select>
  );
}

"use client";

import { useEffect } from "react";

interface DateSelectorProps {
  chipId: string;
  selectedDate: string;
  onDateSelect: (date: string) => void;
  dates?: string[];
  disabled?: boolean;
}

/**
 * Component for selecting a date from available dates
 */
export function DateSelector({
  chipId,
  selectedDate,
  onDateSelect,
  dates,
  disabled = false,
}: DateSelectorProps) {
  // Reset to latest when chip changes
  useEffect(() => {
    if (chipId) {
      onDateSelect("latest");
    }
  }, [chipId, onDateSelect]);

  // Format date string for display (YYYYMMDD -> YYYY/MM/DD)
  const formatDate = (dateStr: string): string => {
    if (dateStr === "latest") return "Latest";
    return `${dateStr.slice(0, 4)}/${dateStr.slice(4, 6)}/${dateStr.slice(
      6,
      8,
    )}`;
  };

  return (
    <div className="form-control w-full max-w-xs">
      <label className="label">
        <span className="label-text">Date</span>
      </label>
      <select
        className="select select-bordered w-full"
        value={selectedDate}
        onChange={(e) => onDateSelect(e.target.value)}
        disabled={disabled}
      >
        <option value="latest">Latest</option>
        {(dates || [])
          .sort((a, b) => b.localeCompare(a)) // Sort dates in descending order
          .map((date) => (
            <option key={date} value={date}>
              {formatDate(date)}
            </option>
          ))}
      </select>
    </div>
  );
}

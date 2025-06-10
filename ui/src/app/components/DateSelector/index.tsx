"use client";

import { useEffect, useMemo } from "react";
import { useFetchChipDates } from "@/client/chip/chip";
import Select, { SingleValue } from "react-select";

interface DateOption {
  value: string;
  label: string;
}

interface DateSelectorProps {
  chipId: string;
  selectedDate: string;
  onDateSelect: (date: string) => void;
  disabled?: boolean;
}

/**
 * Component for selecting a date from available dates
 */
export function DateSelector({
  chipId,
  selectedDate,
  onDateSelect,
  disabled = false,
}: DateSelectorProps) {
  const {
    data: datesResponse,
    isLoading,
    isError,
  } = useFetchChipDates(chipId, {
    query: {
      enabled: !disabled && !!chipId,
    },
  });

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
      8
    )}`;
  };

  const dateOptions = useMemo(() => {
    const dates = ["latest"];
    if (datesResponse?.data?.data && Array.isArray(datesResponse.data.data)) {
      dates.push(...datesResponse.data.data.sort((a, b) => b.localeCompare(a))); // Sort dates in descending order
    }

    return dates.map((date) => ({
      value: date,
      label: formatDate(date),
    }));
  }, [datesResponse]);

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
        <span>Failed to load dates</span>
      </div>
    );
  }

  const handleChange = (option: SingleValue<DateOption>) => {
    if (option) {
      onDateSelect(option.value);
    }
  };

  return (
    <div className="w-full max-w-xs">
      <label className="label">
        <span className="label-text font-medium">Select Date</span>
      </label>
      <Select<DateOption>
        options={dateOptions}
        value={dateOptions.find((option) => option.value === selectedDate)}
        onChange={handleChange}
        placeholder="Select a date"
        className="text-base-content"
        isDisabled={disabled}
      />
    </div>
  );
}

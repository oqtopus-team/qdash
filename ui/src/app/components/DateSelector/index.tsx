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
  isUrlInitialized?: boolean;
}

/**
 * Component for selecting a date from available dates
 */
export function DateSelector({
  chipId,
  selectedDate,
  onDateSelect,
  disabled = false,
  isUrlInitialized = true,
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

  // Don't auto-reset dates - let the parent component handle it

  // Format date string for display (YYYYMMDD -> YYYY/MM/DD)
  const formatDate = (dateStr: string): string => {
    if (dateStr === "latest") return "Latest";
    return `${dateStr.slice(0, 4)}/${dateStr.slice(4, 6)}/${dateStr.slice(
      6,
      8,
    )}`;
  };

  const handleChange = (option: SingleValue<DateOption>) => {
    if (option) {
      onDateSelect(option.value);
    }
  };

  // Always include "latest" option, add other dates if available
  const dateOptions = useMemo(() => {
    const dates = ["latest"];

    // Add additional dates only if they are available and valid
    if (datesResponse?.data?.data && Array.isArray(datesResponse.data.data)) {
      dates.push(...datesResponse.data.data.sort((a, b) => b.localeCompare(a))); // Sort dates in descending order
    }

    return dates.map((date) => ({
      value: date,
      label: formatDate(date),
    }));
  }, [datesResponse]);

  // Don't auto-reset on error - preserve user's selection

  // Show loading state but keep the current selection visible
  if (isLoading) {
    return (
      <div className="w-full max-w-xs">
        <label className="label">
          <span className="label-text font-medium">Select Date</span>
        </label>
        <div className="h-10 bg-base-300 rounded-lg animate-pulse"></div>
      </div>
    );
  }

  // Show error state but keep "latest" option available
  if (isError) {
    return (
      <div className="w-full max-w-xs">
        <label className="label">
          <span className="label-text font-medium">Select Date</span>
        </label>
        <Select<DateOption>
          options={[{ value: "latest", label: "Latest" }]}
          value={{ value: "latest", label: "Latest" }}
          onChange={handleChange}
          isDisabled={disabled}
          className="text-base-content"
        />
        <div className="text-error text-sm mt-2">Failed to load dates</div>
      </div>
    );
  }

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

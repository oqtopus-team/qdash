"use client";

import { useMemo } from "react";

import Select from "react-select";

import type { SingleValue } from "react-select";

import { useGetChipDates } from "@/client/chip/chip";
import { useSelectStyles } from "@/hooks/useSelectStyles";

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

const PLACEHOLDER = "Select a date";

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
  } = useGetChipDates(chipId, {
    query: {
      enabled: !disabled && !!chipId,
    },
  });

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

  const { minWidth, styles } = useSelectStyles<DateOption>({
    labels: dateOptions.map((opt) => opt.label),
    placeholder: PLACEHOLDER,
  });

  // Show loading state but keep the current selection visible
  if (isLoading) {
    return (
      <div className="animate-pulse" style={{ minWidth }}>
        <div className="h-[38px] bg-base-300 rounded"></div>
      </div>
    );
  }

  // Show error state but keep "latest" option available
  if (isError) {
    return (
      <Select<DateOption>
        options={[{ value: "latest", label: "Latest" }]}
        value={{ value: "latest", label: "Latest" }}
        onChange={handleChange}
        isDisabled={disabled}
        className="text-base-content"
        styles={styles}
      />
    );
  }

  return (
    <Select<DateOption>
      options={dateOptions}
      value={dateOptions.find((option) => option.value === selectedDate)}
      onChange={handleChange}
      placeholder={PLACEHOLDER}
      className="text-base-content"
      isDisabled={disabled}
      styles={styles}
    />
  );
}

"use client";

import { useEffect, useState } from "react";

interface DateSelectorProps {
  selectedDate: string;
  onDateSelect: (date: string) => void;
  disabled?: boolean;
}

export function DateSelector({
  selectedDate,
  onDateSelect,
  disabled = false,
}: DateSelectorProps) {
  const [dates, setDates] = useState<string[]>([]);

  // In a real implementation, we would fetch the available dates from the API
  // For now, let's generate some sample dates
  useEffect(() => {
    const generateDates = () => {
      const today = new Date();
      const dates = ["latest"];
      for (let i = 0; i < 7; i++) {
        const date = new Date();
        date.setDate(today.getDate() - i);
        dates.push(date.toISOString().split("T")[0]);
      }
      return dates;
    };

    setDates(generateDates());
  }, []);

  return (
    <select
      className="select select-bordered w-full max-w-xs"
      value={selectedDate}
      onChange={(e) => onDateSelect(e.target.value)}
      disabled={disabled}
    >
      {dates.map((date) => (
        <option key={date} value={date}>
          {date === "latest" ? "Latest" : date}
        </option>
      ))}
    </select>
  );
}

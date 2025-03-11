"use client";

import { useEffect, useState } from "react";

interface DateTimePickerProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}

export function DateTimePicker({
  label,
  value,
  onChange,
  disabled = false,
}: DateTimePickerProps) {
  // Convert ISO string to local datetime string
  const toLocalDateTimeString = (isoString: string) => {
    const date = new Date(isoString);
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    const hours = String(date.getHours()).padStart(2, "0");
    const minutes = String(date.getMinutes()).padStart(2, "0");
    return `${year}-${month}-${day}T${hours}:${minutes}`;
  };

  const [localValue, setLocalValue] = useState(toLocalDateTimeString(value));

  useEffect(() => {
    setLocalValue(toLocalDateTimeString(value));
  }, [value]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newValue = e.target.value;
    setLocalValue(newValue);
    // Convert local time to ISO string with JST timezone
    const date = new Date(newValue);
    // Format as YYYY-MM-DDTHH:mm:ss.SSSZ+09:00
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, "0");
    const day = String(date.getDate()).padStart(2, "0");
    const hours = String(date.getHours()).padStart(2, "0");
    const minutes = String(date.getMinutes()).padStart(2, "0");
    const seconds = String(date.getSeconds()).padStart(2, "0");
    const milliseconds = String(date.getMilliseconds()).padStart(3, "0");
    const jstString = `${year}-${month}-${day}T${hours}:${minutes}:${seconds}.${milliseconds}+09:00`;
    onChange(jstString);
  };

  return (
    <div className="form-control w-full">
      <label className="label">
        <span className="label-text">{label}</span>
      </label>
      <input
        type="datetime-local"
        className="input input-bordered w-full"
        value={localValue}
        onChange={handleChange}
        disabled={disabled}
      />
    </div>
  );
}

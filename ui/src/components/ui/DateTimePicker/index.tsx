"use client";

import { useEffect, useState } from "react";

import { toDateTimeLocal, toIsoSeconds } from "@/lib/utils/datetime";

interface DateTimePickerProps {
  label: string;
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}

export function DateTimePicker({ label, value, onChange, disabled = false }: DateTimePickerProps) {
  const [localValue, setLocalValue] = useState(toDateTimeLocal(value));

  useEffect(() => {
    setLocalValue(toDateTimeLocal(value));
  }, [value]);

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const newValue = e.target.value;
    setLocalValue(newValue);
    onChange(toIsoSeconds(newValue));
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

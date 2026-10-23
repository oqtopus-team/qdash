"use client";

import {
  SWEEP_ARGUMENT_NAMES,
  SWEEP_FORM_TYPES,
  describeSweep,
  type SweepFormType,
} from "@/lib/utils/task-parameters";

interface SweepParameterFieldProps {
  name: string;
  unit: string;
  description: string;
  /** The form the parameter declares; the form the run uses may differ. */
  declaredType: SweepFormType;
  type: SweepFormType;
  /** The three constructor arguments as typed, used by every form but `list`. */
  parts: readonly string[];
  /** The explicit points as a JSON array, used by the `list` form. */
  listValue: string;
  onTypeChange: (type: SweepFormType) => void;
  onPartChange: (index: number, value: string) => void;
  onListChange: (value: string) => void;
}

/** Returns the JSON value a sweep field holds, or null when it is blank or malformed. */
export function sweepFieldValue(
  type: SweepFormType,
  parts: readonly string[],
  listValue: string,
): unknown[] | null {
  if (type === "list") {
    try {
      const parsed: unknown = JSON.parse(listValue);
      return Array.isArray(parsed) ? parsed : null;
    } catch {
      return null;
    }
  }
  if (parts.length !== 3 || parts.some((part) => part.trim() === "")) return null;
  return parts.map((part) => Number(part));
}

/** One run parameter that declares a generated range: its form, arguments, and the points. */
export function SweepParameterField({
  name,
  unit,
  description,
  declaredType,
  type,
  parts,
  listValue,
  onTypeChange,
  onPartChange,
  onListChange,
}: SweepParameterFieldProps) {
  const value = sweepFieldValue(type, parts, listValue);
  const summary = value === null ? null : describeSweep(type, value);
  const isBlank =
    type === "list" ? listValue.trim() === "" : parts.every((part) => part.trim() === "");
  return (
    <div className="form-control min-w-0">
      <span className="label-text mb-1 flex min-w-0 items-start justify-between gap-2">
        <span className="min-w-0 break-words">{name}</span>
        <span className="max-w-[45%] shrink-0 break-all text-right text-base-content/40">
          {unit}
        </span>
      </span>
      <select
        aria-label={`${name} type`}
        className="select select-sm select-bordered w-full font-mono"
        value={type}
        onChange={(event) => onTypeChange(event.target.value as SweepFormType)}
      >
        {SWEEP_FORM_TYPES.map((option) => (
          <option key={option} value={option}>
            {option === declaredType ? `${option} (default)` : option}
          </option>
        ))}
      </select>
      {type === "list" ? (
        <input
          aria-label={`${name} values`}
          className="input input-sm input-bordered mt-2 w-full font-mono"
          value={listValue}
          placeholder="[0, 4, 16, 64]"
          onChange={(event) => onListChange(event.target.value)}
        />
      ) : (
        <div className="mt-2 grid grid-cols-3 gap-2">
          {SWEEP_ARGUMENT_NAMES[type].map((argument, index) => (
            <label key={argument} className="flex min-w-0 flex-col gap-1">
              <span className="truncate text-xs text-base-content/50">{argument}</span>
              <input
                aria-label={`${name} ${argument}`}
                className="input input-sm input-bordered w-full min-w-0 px-2 font-mono"
                value={parts[index] ?? ""}
                onChange={(event) => onPartChange(index, event.target.value)}
              />
            </label>
          ))}
        </div>
      )}
      <span className="mt-1 break-words text-xs text-base-content/45">
        {isBlank ? (
          "Blank runs the task default."
        ) : summary === null ? (
          <span className="text-error">Enter numbers that produce a sweep.</span>
        ) : (
          summary
        )}
        {description ? ` ${description}` : ""}
      </span>
    </div>
  );
}

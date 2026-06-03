"use client";

import { Search, X } from "lucide-react";

interface SearchInputProps {
  /** Current input value */
  value: string;
  /** Called with the new value on every keystroke */
  onChange: (value: string) => void;
  /**
   * Called when the clear (X) button is clicked.
   * Defaults to clearing the value via `onChange("")`.
   */
  onClear?: () => void;
  /** Placeholder text */
  placeholder?: string;
  /**
   * Additional CSS classes applied to the wrapping label.
   * Use this to control width, e.g. `"w-full max-w-sm"` or `"flex-1 max-w-sm"`.
   */
  className?: string;
}

/**
 * Search/filter text input with a leading search icon and a clear button.
 *
 * Renders as a DaisyUI `input` label so the icon and clear button stay aligned
 * with the field. Shared across list/search pages for a consistent look.
 */
export function SearchInput({
  value,
  onChange,
  onClear,
  placeholder,
  className = "w-full max-w-sm",
}: SearchInputProps) {
  const handleClear = onClear ?? (() => onChange(""));

  return (
    <label className={`input input-bordered input-sm flex items-center gap-2 ${className}`}>
      <Search className="h-4 w-4 shrink-0 text-base-content/40" />
      <input
        type="text"
        className="grow"
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
      />
      {value && (
        <button
          type="button"
          onClick={handleClear}
          className="btn btn-ghost btn-xs p-0 h-auto min-h-0 shrink-0"
        >
          <X className="h-3 w-3" />
        </button>
      )}
    </label>
  );
}

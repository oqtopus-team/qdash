"use client";

import { Search, X } from "lucide-react";
import { useEffect, useRef } from "react";

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
  const inputRef = useRef<HTMLInputElement>(null);
  const handleClear = () => {
    if (onClear) onClear();
    else onChange("");
    inputRef.current?.focus();
  };

  useEffect(() => {
    const handleKeyDown = (event: KeyboardEvent) => {
      if (
        event.key !== "/" ||
        event.defaultPrevented ||
        event.isComposing ||
        event.repeat ||
        event.ctrlKey ||
        event.metaKey ||
        event.altKey
      )
        return;

      const activeElement = document.activeElement;
      if (
        activeElement?.closest(
          'input, textarea, select, [contenteditable]:not([contenteditable="false"]), [role="textbox"], [role="combobox"], [role="menu"]',
        ) ||
        document.querySelector('[role="dialog"], [role="alertdialog"], dialog[open]')
      )
        return;

      const input = inputRef.current;
      if (!input || input.getClientRects().length === 0) return;
      event.preventDefault();
      input.focus();
      input.select();
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, []);

  return (
    <label className={`input input-bordered input-sm flex items-center gap-2 ${className}`}>
      <Search className="h-4 w-4 shrink-0 text-base-content/40" />
      <input
        ref={inputRef}
        type="text"
        aria-label={placeholder || "Search"}
        aria-keyshortcuts="/"
        className="grow"
        placeholder={placeholder}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Escape" && !event.nativeEvent.isComposing && value) {
            event.preventDefault();
            event.stopPropagation();
            handleClear();
          }
        }}
      />
      <kbd
        className="hidden rounded border border-base-300 px-1 text-xs text-base-content/60 sm:inline"
        title="Press / to focus search; Esc to clear"
        aria-hidden="true"
      >
        /
      </kbd>
      {value && (
        <button
          type="button"
          onClick={handleClear}
          aria-label="Clear search"
          title="Clear search (Esc)"
          className="btn btn-ghost btn-xs p-0 h-auto min-h-0 shrink-0"
        >
          <X className="h-3 w-3" />
        </button>
      )}
    </label>
  );
}

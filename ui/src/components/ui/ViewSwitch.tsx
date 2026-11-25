"use client";

import { useRef, type KeyboardEvent, type ReactNode } from "react";

export interface ViewSwitchItem<T extends string> {
  value: T;
  label: ReactNode;
  /** Leading Lucide icon, sized to 1rem; mark it `aria-hidden`. */
  icon?: ReactNode;
  /** Accessible name when `label` is visually hidden or not plain text. */
  ariaLabel?: string;
  title?: string;
}

type ViewSwitchSize = "xs" | "sm" | "md";

interface ViewSwitchProps<T extends string> {
  items: readonly ViewSwitchItem<T>[];
  /** Current view; a value outside `items` selects no tab. */
  value: string;
  onValueChange: (value: T) => void;
  /** Accessible name of the tab list, for example "Chip view". */
  ariaLabel: string;
  size?: ViewSwitchSize;
  className?: string;
}

// Literal class names keep the daisyUI tab size classes visible to Tailwind's scanner.
const SIZE_CLASS: Record<ViewSwitchSize, string> = {
  xs: "tabs-xs",
  sm: "tabs-sm",
  md: "tabs-md",
};

/**
 * Segmented switch between views that render inline on the same page.
 *
 * It renders static daisyUI tabs with the `tabs-boxed` rules in `globals.css`: a subdued
 * base-200 track and a base-100 surface on the selected tab. Selection follows focus with
 * Arrow, Home, and End keys, and clicking the selected tab calls `onValueChange` again so
 * callers can treat it as a reset action.
 */
export function ViewSwitch<T extends string>({
  items,
  value,
  onValueChange,
  ariaLabel,
  size = "md",
  className = "",
}: ViewSwitchProps<T>) {
  const buttonRefs = useRef<(HTMLButtonElement | null)[]>([]);
  const selectedIndex = items.findIndex((item) => item.value === value);
  // A value outside the rendered items (for example a hidden conditional view) keeps the
  // first item reachable with Tab.
  const focusableIndex = selectedIndex === -1 ? 0 : selectedIndex;

  const selectAt = (index: number, activate = false) => {
    const item = items[index];
    if (!item) return;
    buttonRefs.current[index]?.focus();
    if (activate || item.value !== value) onValueChange(item.value);
  };

  const handleKeyDown = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const last = items.length - 1;
    let next: number;
    switch (event.key) {
      case "ArrowRight":
        next = index === last ? 0 : index + 1;
        break;
      case "ArrowLeft":
        next = index === 0 ? last : index - 1;
        break;
      case "Home":
        next = 0;
        break;
      case "End":
        next = last;
        break;
      default:
        return;
    }
    event.preventDefault();
    selectAt(next);
  };

  return (
    <div
      role="tablist"
      aria-label={ariaLabel}
      aria-orientation="horizontal"
      className={`tabs tabs-boxed ${SIZE_CLASS[size]} w-fit max-w-full flex-nowrap gap-1 ${className}`}
    >
      {items.map((item, index) => {
        const selected = index === selectedIndex;
        return (
          <button
            key={item.value}
            ref={(element) => {
              buttonRefs.current[index] = element;
            }}
            type="button"
            role="tab"
            aria-selected={selected}
            aria-label={item.ariaLabel}
            title={item.title}
            tabIndex={index === focusableIndex ? 0 : -1}
            className={`tab shrink-0 gap-1.5 whitespace-nowrap [&>svg]:size-4 [&>svg]:shrink-0 ${selected ? "tab-active" : ""}`}
            onClick={() => selectAt(index, true)}
            onKeyDown={(event) => handleKeyDown(event, index)}
          >
            {item.icon}
            {item.label}
          </button>
        );
      })}
    </div>
  );
}

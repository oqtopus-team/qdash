"use client";

import { useRef, type KeyboardEvent, type ReactNode } from "react";

export interface ViewSwitchItem<T extends string> {
  value: T;
  label: ReactNode;
  /** Leading Lucide icon; it is hidden from assistive technology. */
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

// Literal class names keep the daisyUI megamenu size classes visible to Tailwind's scanner.
const SIZE_CLASS: Record<ViewSwitchSize, string> = {
  xs: "megamenu-xs p-1",
  sm: "megamenu-sm p-1",
  md: "megamenu-md p-2",
};

/**
 * Segmented switch between views that render inline on the same page.
 *
 * It uses the daisyUI megamenu with plain direct-child buttons, so items need no popovers.
 * The `view-switch` rules in `globals.css` keep the moving indicator on the selected item
 * while no item is hovered. Selection follows focus with Arrow, Home, and End keys.
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
      className={`megamenu view-switch ${SIZE_CLASS[size]} border border-base-300 w-fit max-w-full ${className}`}
    >
      <span className="megamenu-active" aria-hidden="true" />
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

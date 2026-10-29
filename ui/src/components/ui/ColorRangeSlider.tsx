"use client";

import { type KeyboardEvent, useId, useState } from "react";

import { RotateCcw } from "lucide-react";

import {
  type ColorRange,
  colorRangeSpinnerStep,
  colorRangeStep,
  formatRangeValue,
} from "@/lib/utils/color-scale";

interface ColorRangeSliderProps {
  /** Whole interval the thumbs can travel. */
  bounds: ColorRange;
  /** Interval currently mapped onto the palette. */
  value: ColorRange;
  /** True when `value` differs from the metric's default range. */
  isOverridden: boolean;
  unit: string;
  colors: string[];
  onChange: (range: ColorRange) => void;
  onReset: () => void;
}

// DaisyUI's range styles the thumb; the track and fill are hidden so the gradient
// bar underneath shows through, and only the thumbs accept pointer events so the
// two overlapping inputs do not block each other.
const THUMB_INPUT_CLASS = [
  "range range-xs range-primary pointer-events-none absolute inset-0 h-full w-full",
  "[--range-bg:transparent] [--range-fill:0]",
  "[&::-webkit-slider-thumb]:pointer-events-auto [&::-moz-range-thumb]:pointer-events-auto",
].join(" ");

interface BoundInputProps {
  value: number;
  /** Resolution used to format the value; matches the thumbs. */
  step: number;
  /** Increment for the spinner arrows and arrow keys. */
  spinnerStep: number;
  ariaLabel: string;
  onCommit: (raw: string) => void;
}

/**
 * Number field for one end of the range. Every edit (typing, spinner arrows,
 * arrow keys) commits at once so the slider and heatmap follow immediately.
 * While focused the field shows what the user typed, even when the committed
 * value was clamped; on blur it snaps to the committed value.
 */
function BoundInput({ value, step, spinnerStep, ariaLabel, onCommit }: BoundInputProps) {
  const formatted = formatRangeValue(value, step);
  const [draft, setDraft] = useState<string | null>(null);
  const blurOnEnter = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") e.currentTarget.blur();
  };
  return (
    <input
      type="number"
      className="input input-xs w-24 shrink-0 font-mono tabular-nums"
      aria-label={ariaLabel}
      step={spinnerStep}
      value={draft ?? formatted}
      onFocus={() => setDraft(formatted)}
      onChange={(e) => {
        const raw = e.target.value;
        setDraft(raw);
        if (raw.trim() !== "" && Number.isFinite(Number(raw))) onCommit(raw);
      }}
      onBlur={() => setDraft(null)}
      onKeyDown={blurOnEnter}
    />
  );
}

/**
 * Two-thumb slider that sets the interval a metric heatmap maps onto the
 * palette. The track previews the palette between the thumbs; values beyond a
 * thumb take the palette's end color, shown dimmed on either side.
 */
export function ColorRangeSlider({
  bounds,
  value,
  isOverridden,
  unit,
  colors,
  onChange,
  onReset,
}: ColorRangeSliderProps) {
  const id = useId();
  const span = bounds.max - bounds.min;
  const step = colorRangeStep(bounds);
  const spinnerStep = colorRangeSpinnerStep(bounds);
  const toPct = (v: number) => (span > 0 ? ((v - bounds.min) / span) * 100 : 0);
  const minPct = Math.max(0, Math.min(100, toPct(value.min)));
  const maxPct = Math.max(0, Math.min(100, toPct(value.max)));
  const first = colors[0] ?? "transparent";
  const last = colors[colors.length - 1] ?? "transparent";
  const gradient = `linear-gradient(to right, ${colors.join(", ")})`;

  const clampMin = (next: number) => Math.min(Math.max(bounds.min, next), value.max - step);
  const clampMax = (next: number) => Math.max(Math.min(bounds.max, next), value.min + step);

  const handleMin = (raw: string) => {
    const next = Number(raw);
    if (!Number.isFinite(next)) return;
    onChange({ min: clampMin(next), max: value.max });
  };
  const handleMax = (raw: string) => {
    const next = Number(raw);
    if (!Number.isFinite(next)) return;
    onChange({ min: value.min, max: clampMax(next) });
  };

  const unitSuffix = unit ? ` ${unit}` : "";
  return (
    <div
      className="flex w-full max-w-xl flex-wrap items-center gap-x-3 gap-y-2 text-xs"
      data-testid="color-range-slider"
    >
      <span id={`${id}-label`} className="shrink-0 font-medium text-base-content/70">
        Color range
      </span>
      <BoundInput
        value={value.min}
        step={step}
        spinnerStep={spinnerStep}
        ariaLabel={`Color range minimum value${unitSuffix}`}
        onCommit={handleMin}
      />
      <div className="relative h-4 min-w-32 flex-1" role="group" aria-labelledby={`${id}-label`}>
        <div
          className="pointer-events-none absolute inset-x-0 top-1/2 h-2 -translate-y-1/2 overflow-hidden rounded-full"
          aria-hidden="true"
        >
          <div className="absolute inset-0 opacity-30" style={{ background: first }} />
          <div
            className="absolute inset-y-0 opacity-30"
            style={{ left: `${maxPct}%`, right: 0, background: last }}
          />
          <div
            className="absolute inset-y-0"
            style={{
              left: `${minPct}%`,
              width: `${Math.max(0, maxPct - minPct)}%`,
              background: gradient,
            }}
          />
        </div>
        <input
          type="range"
          className={THUMB_INPUT_CLASS}
          aria-label={`Color range minimum${unitSuffix}`}
          aria-valuetext={`${formatRangeValue(value.min, step)}${unitSuffix}`}
          min={bounds.min}
          max={bounds.max}
          step={step}
          value={value.min}
          onChange={(e) => handleMin(e.target.value)}
        />
        <input
          type="range"
          className={THUMB_INPUT_CLASS}
          aria-label={`Color range maximum${unitSuffix}`}
          aria-valuetext={`${formatRangeValue(value.max, step)}${unitSuffix}`}
          min={bounds.min}
          max={bounds.max}
          step={step}
          value={value.max}
          onChange={(e) => handleMax(e.target.value)}
        />
      </div>
      <BoundInput
        value={value.max}
        step={step}
        spinnerStep={spinnerStep}
        ariaLabel={`Color range maximum value${unitSuffix}`}
        onCommit={handleMax}
      />
      {unit && <span className="shrink-0 text-base-content/50">{unit}</span>}
      <button
        type="button"
        className="btn btn-ghost btn-xs gap-1"
        onClick={onReset}
        disabled={!isOverridden}
        title="Reset color range to default"
      >
        <RotateCcw className="h-3 w-3" aria-hidden="true" />
        Reset
      </button>
    </div>
  );
}

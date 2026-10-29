"use client";

import { type KeyboardEvent, useId } from "react";

import { RotateCcw } from "lucide-react";

import { type ColorRange, colorRangeStep, formatRangeValue } from "@/lib/utils/color-scale";

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
  const blurOnEnter = (e: KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter") e.currentTarget.blur();
  };

  return (
    <div
      className="flex w-full max-w-xl flex-wrap items-center gap-x-3 gap-y-2 text-xs"
      data-testid="color-range-slider"
    >
      <span id={`${id}-label`} className="shrink-0 font-medium text-base-content/70">
        Color range
      </span>
      <input
        key={`min-${formatRangeValue(value.min, step)}`}
        type="number"
        className="input input-xs w-24 shrink-0 font-mono tabular-nums"
        aria-label={`Color range minimum value${unitSuffix}`}
        step={step}
        defaultValue={formatRangeValue(value.min, step)}
        onBlur={(e) => handleMin(e.target.value)}
        onKeyDown={blurOnEnter}
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
      <input
        key={`max-${formatRangeValue(value.max, step)}`}
        type="number"
        className="input input-xs w-24 shrink-0 font-mono tabular-nums"
        aria-label={`Color range maximum value${unitSuffix}`}
        step={step}
        defaultValue={formatRangeValue(value.max, step)}
        onBlur={(e) => handleMax(e.target.value)}
        onKeyDown={blurOnEnter}
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

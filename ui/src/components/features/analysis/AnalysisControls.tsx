"use client";

import { ViewSwitch } from "@/components/ui/ViewSwitch";
import type { SelectionMode } from "@/hooks/url-state/types";

export type MetricType = "qubit" | "coupling";

/** Whether a metric is stored as a fraction and displayed as a percentage. */
export function isPercentageMetric(unit: string | undefined): boolean {
  return unit === "%";
}

interface MetricTypeSwitchProps {
  value: MetricType;
  onValueChange: (value: MetricType) => void;
}

/** 1Q/2Q switch between qubit and coupling metrics. */
export function MetricTypeSwitch({ value, onValueChange }: MetricTypeSwitchProps) {
  return (
    <ViewSwitch
      ariaLabel="Metric target"
      size="sm"
      value={value}
      onValueChange={onValueChange}
      items={[
        { value: "qubit", label: "1Q", title: "Qubit" },
        { value: "coupling", label: "2Q", title: "Coupling" },
      ]}
    />
  );
}

interface SelectionModeToggleProps {
  value: SelectionMode;
  onChange: (mode: SelectionMode) => void;
  isBestModeSupported: boolean;
}

/** Latest/Best/Average choice of which calibration value represents each target. */
export function SelectionModeToggle({
  value,
  onChange,
  isBestModeSupported,
}: SelectionModeToggleProps) {
  return (
    <div className="join">
      <button
        className={`join-item btn btn-sm ${value === "latest" ? "btn-primary" : ""}`}
        onClick={() => onChange("latest")}
      >
        Latest
      </button>
      <button
        className={`join-item btn btn-sm ${value === "best" ? "btn-primary" : ""} ${!isBestModeSupported ? "btn-disabled" : ""}`}
        onClick={() => onChange("best")}
        disabled={!isBestModeSupported}
        title={!isBestModeSupported ? "Best mode not available" : "Show best values"}
      >
        Best
      </button>
      <button
        className={`join-item btn btn-sm ${value === "average" ? "btn-primary" : ""}`}
        onClick={() => onChange("average")}
        title="Show average values"
      >
        Average
      </button>
    </div>
  );
}

interface ErrorRateToggleProps {
  checked: boolean;
  onChange: (showAsErrorRate: boolean) => void;
}

/** Fidelity/Error switch for percentage metrics. */
export function ErrorRateToggle({ checked, onChange }: ErrorRateToggleProps) {
  return (
    <label className="choice-field text-sm">
      <span className="text-sm">Fidelity</span>
      <input
        type="checkbox"
        className="toggle toggle-primary toggle-xs sm:toggle-sm"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
      />
      <span className="text-sm">Error</span>
    </label>
  );
}

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ErrorRateToggle,
  MetricTypeSwitch,
  SelectionModeToggle,
  isPercentageMetric,
} from "@/components/features/analysis/AnalysisControls";

afterEach(() => cleanup());

describe("isPercentageMetric", () => {
  it("treats only the percent unit as a percentage", () => {
    expect(isPercentageMetric("%")).toBe(true);
    expect(isPercentageMetric("us")).toBe(false);
    expect(isPercentageMetric(undefined)).toBe(false);
  });
});

describe("MetricTypeSwitch", () => {
  it("switches between qubit and coupling metrics", () => {
    const onValueChange = vi.fn();
    render(<MetricTypeSwitch value="qubit" onValueChange={onValueChange} />);

    expect(screen.getByRole("tablist", { name: "Metric target" })).not.toBeNull();
    fireEvent.click(screen.getByRole("tab", { name: "2Q" }));
    expect(onValueChange).toHaveBeenCalledWith("coupling");
  });
});

describe("SelectionModeToggle", () => {
  it("highlights the current mode and reports a new one", () => {
    const onChange = vi.fn();
    render(<SelectionModeToggle value="average" onChange={onChange} isBestModeSupported />);

    expect(screen.getByRole("button", { name: "Average" }).className).toContain("btn-primary");
    expect(screen.getByRole("button", { name: "Latest" }).className).not.toContain("btn-primary");
    fireEvent.click(screen.getByRole("button", { name: "Best" }));
    expect(onChange).toHaveBeenCalledWith("best");
  });

  it("disables Best when the metric has no best value", () => {
    render(<SelectionModeToggle value="latest" onChange={vi.fn()} isBestModeSupported={false} />);
    const best = screen.getByRole("button", { name: "Best" }) as HTMLButtonElement;

    expect(best.disabled).toBe(true);
    expect(best.title).toBe("Best mode not available");
  });
});

describe("ErrorRateToggle", () => {
  it("reports the Error position of the Fidelity/Error switch", () => {
    const onChange = vi.fn();
    render(<ErrorRateToggle checked={false} onChange={onChange} />);

    fireEvent.click(screen.getByRole("checkbox"));
    expect(onChange).toHaveBeenCalledWith(true);
  });
});

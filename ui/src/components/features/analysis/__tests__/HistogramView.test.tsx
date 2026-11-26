import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { parse } from "yaml";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { HistogramView } from "@/components/features/analysis/HistogramView";

// Serve the checked-in metrics configuration so the slider bounds come from the real YAML.
const metricsConfig = parse(
  readFileSync(resolve(__dirname, "../../../../../../config/domain/metrics.yaml"), "utf8"),
) as Record<string, unknown>;

const urlState = vi.hoisted(() => ({
  showAsErrorRate: false,
  setCustomThreshold: vi.fn(),
}));

vi.mock("@/client/metrics/metrics", () => ({
  useGetMetricsConfig: () => ({
    data: { data: metricsConfig },
    isLoading: false,
    isError: false,
    error: null,
    isFetching: false,
    errorUpdateCount: 0,
    refetch: vi.fn(),
  }),
  useGetChipMetrics: () => ({ data: undefined, isLoading: false, isError: false, error: null }),
}));

vi.mock("@/client/chip/chip", () => ({
  useListChips: () => ({ data: undefined }),
}));

vi.mock("@/hooks/useUrlState", () => ({
  useHistogramUrlState: () => ({
    selectedChip: "chip-1",
    selectionMode: "latest",
    selectedParameter: "average_readout_fidelity",
    showAsErrorRate: urlState.showAsErrorRate,
    customThreshold: null,
    setSelectedChip: vi.fn(),
    setSelectionMode: vi.fn(),
    setSelectedParameter: vi.fn(),
    setShowAsErrorRate: vi.fn(),
    setCustomThreshold: urlState.setCustomThreshold,
    isInitialized: true,
  }),
  useRangeModeUrlState: () => ({
    startDate: "",
    endDate: "",
    setStartDate: vi.fn(),
    setEndDate: vi.fn(),
    setQuickRange: vi.fn(),
  }),
}));

vi.mock("@/contexts/ThemeContext", () => ({ useIsDarkTheme: () => false }));
vi.mock("@/components/selectors/ChipSelector", () => ({ ChipSelector: () => null }));
vi.mock("@/components/ui/TimeRangeSelector", () => ({ TimeRangeSelector: () => null }));
vi.mock("@/components/charts/PlotCard", () => ({ PlotCard: () => null }));

function renderSlider() {
  render(<HistogramView />);
  return screen.getByRole("slider") as HTMLInputElement;
}

beforeEach(() => {
  urlState.showAsErrorRate = false;
  urlState.setCustomThreshold.mockReset();
});

afterEach(() => cleanup());

describe("HistogramView average readout fidelity threshold", () => {
  it("lets the fidelity threshold reach 100%", () => {
    const slider = renderSlider();

    expect(screen.getByText("Threshold: 99.00%")).not.toBeNull();
    expect(Number(slider.min)).toBe(90);
    expect(Number(slider.max)).toBe(100);
    expect(screen.getByText("100%")).not.toBeNull();

    fireEvent.change(slider, { target: { value: "100" } });
    expect(urlState.setCustomThreshold).toHaveBeenCalledWith(1);
  });

  it("lets the error-rate threshold reach 0%", () => {
    urlState.showAsErrorRate = true;
    const slider = renderSlider();

    expect(screen.getByText("Threshold: 1.00%")).not.toBeNull();
    expect(Number(slider.min)).toBe(0);
    expect(screen.getByText("0%")).not.toBeNull();

    fireEvent.change(slider, { target: { value: "0" } });
    expect(urlState.setCustomThreshold).toHaveBeenCalledWith(1);
  });
});

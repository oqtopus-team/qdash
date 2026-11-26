import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { parse } from "yaml";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { HistogramView } from "@/components/features/analysis/HistogramView";

// Serve the checked-in metrics configuration so the slider bounds come from the real YAML.
const checkedInMetricsConfig = parse(
  readFileSync(resolve(__dirname, "../../../../../../config/domain/metrics.yaml"), "utf8"),
) as MetricsConfigYaml;

type MetricsConfigYaml = Record<string, Record<string, Record<string, unknown>>>;

const urlState = vi.hoisted(() => ({
  metricsConfig: {} as Record<string, unknown>,
  selectedParameter: "average_readout_fidelity",
  showAsErrorRate: false,
  customThreshold: null as number | null,
  setCustomThreshold: vi.fn(),
}));

vi.mock("@/client/metrics/metrics", () => ({
  useGetMetricsConfig: () => ({
    data: { data: urlState.metricsConfig },
    isLoading: false,
    isError: false,
    error: null,
    isFetching: false,
    errorUpdateCount: 0,
    refetch: vi.fn(),
  }),
  useGetChipMetrics: () => ({
    data: undefined,
    isLoading: false,
    isError: false,
    error: null,
  }),
}));

vi.mock("@/client/chip/chip", () => ({
  useListChips: () => ({ data: undefined }),
}));

vi.mock("@/hooks/useUrlState", () => ({
  useHistogramUrlState: () => ({
    selectedChip: "chip-1",
    selectionMode: "latest",
    selectedParameter: urlState.selectedParameter,
    showAsErrorRate: urlState.showAsErrorRate,
    customThreshold: urlState.customThreshold,
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
vi.mock("@/components/selectors/ChipSelector", () => ({
  ChipSelector: () => null,
}));
vi.mock("@/components/ui/TimeRangeSelector", () => ({
  TimeRangeSelector: () => null,
}));
vi.mock("@/components/charts/PlotCard", () => ({ PlotCard: () => null }));

function renderSlider() {
  render(<HistogramView />);
  return screen.getByRole("slider") as HTMLInputElement;
}

/** Copy of the checked-in config with one metric's threshold range replaced. */
function withThresholdRange(
  group: "qubit_metrics" | "coupling_metrics",
  key: string,
  range: { min: number; max: number; step: number },
): Record<string, unknown> {
  const config = structuredClone(checkedInMetricsConfig);
  const metric = config[group][key];
  metric.threshold = {
    ...(metric.threshold as Record<string, unknown>),
    range,
  };
  return config;
}

beforeEach(() => {
  urlState.metricsConfig = checkedInMetricsConfig;
  urlState.selectedParameter = "average_readout_fidelity";
  urlState.showAsErrorRate = false;
  urlState.customThreshold = null;
  urlState.setCustomThreshold.mockReset();
});

afterEach(() => cleanup());

// Display-unit expectations derived from config/domain/metrics.yaml (issue #594).
const fidelityMetrics = [
  {
    key: "average_readout_fidelity",
    min: 90,
    step: 0.1,
    fidelity: "99.00%",
    error: "1.00%",
  },
  {
    key: "average_gate_fidelity",
    min: 90,
    step: 0.01,
    fidelity: "99.90%",
    error: "0.10%",
  },
  {
    key: "x90_gate_fidelity",
    min: 90,
    step: 0.01,
    fidelity: "99.90%",
    error: "0.10%",
  },
  {
    key: "x180_gate_fidelity",
    min: 90,
    step: 0.01,
    fidelity: "99.90%",
    error: "0.10%",
  },
  {
    key: "zx90_gate_fidelity",
    min: 90,
    step: 0.1,
    fidelity: "99.00%",
    error: "1.00%",
  },
  {
    key: "bell_state_fidelity",
    min: 80,
    step: 0.1,
    fidelity: "95.00%",
    error: "5.00%",
  },
];

describe.each(fidelityMetrics)("HistogramView $key threshold", (metric) => {
  beforeEach(() => {
    urlState.selectedParameter = metric.key;
  });

  it("lets the fidelity threshold reach 100%", () => {
    const slider = renderSlider();

    expect(screen.getByText(`Threshold: ${metric.fidelity}`)).not.toBeNull();
    expect(Number(slider.min)).toBe(metric.min);
    expect(Number(slider.max)).toBe(100);
    expect(Number(slider.step)).toBe(metric.step);
    expect(screen.getByText(`${metric.min}%`)).not.toBeNull();
    expect(screen.getByText("100%")).not.toBeNull();

    fireEvent.change(slider, { target: { value: "100" } });
    expect(urlState.setCustomThreshold).toHaveBeenLastCalledWith(1);

    // One step below 100% carries floating-point noise without normalization
    // (99.9 / 100 = 0.9990000000000001, 99.99 / 100 = 0.9998999999999999).
    const nearMax =
      metric.step === 0.01 ? { display: "99.99", raw: 0.9999 } : { display: "99.9", raw: 0.999 };
    fireEvent.change(slider, { target: { value: nearMax.display } });
    expect(urlState.setCustomThreshold).toHaveBeenLastCalledWith(nearMax.raw);
  });

  it("lets the error-rate threshold reach 0%", () => {
    urlState.showAsErrorRate = true;
    const slider = renderSlider();
    const maxError = 100 - metric.min;

    expect(screen.getByText(`Threshold: ${metric.error}`)).not.toBeNull();
    expect(Number(slider.min)).toBe(0);
    expect(Number(slider.max)).toBe(maxError);
    expect(Number(slider.step)).toBe(metric.step);
    expect(screen.getByText("0%")).not.toBeNull();
    expect(screen.getByText(`${maxError}%`)).not.toBeNull();

    fireEvent.change(slider, { target: { value: "0" } });
    expect(urlState.setCustomThreshold).toHaveBeenLastCalledWith(1);

    fireEvent.change(slider, { target: { value: String(maxError) } });
    expect(urlState.setCustomThreshold).toHaveBeenLastCalledWith(metric.min / 100);
  });
});

describe("HistogramView threshold precision", () => {
  it("shows fractional GHz thresholds at the slider step precision", () => {
    urlState.selectedParameter = "readout_frequency";
    urlState.customThreshold = 7.01;
    const slider = renderSlider();

    expect(screen.getByText("Threshold: 7.01 GHz")).not.toBeNull();
    expect(Number(slider.value)).toBe(7.01);
    expect(screen.getByText("6")).not.toBeNull();
    expect(screen.getByText("10")).not.toBeNull();
  });

  it("keeps the default GHz threshold at two decimals", () => {
    urlState.selectedParameter = "qubit_frequency";
    renderSlider();

    expect(screen.getByText("Threshold: 5.00 GHz")).not.toBeNull();
  });

  it("shows fractional qubit frequency thresholds", () => {
    urlState.selectedParameter = "qubit_frequency";
    urlState.customThreshold = 5.01;
    renderSlider();

    expect(screen.getByText("Threshold: 5.01 GHz")).not.toBeNull();
  });

  it("shows fractional non-percent slider endpoints", () => {
    urlState.metricsConfig = withThresholdRange("qubit_metrics", "qubit_frequency", {
      min: 4.25,
      max: 5.75,
      step: 0.05,
    });
    urlState.selectedParameter = "qubit_frequency";
    urlState.customThreshold = 5.05;
    const slider = renderSlider();

    expect(screen.getByText("Threshold: 5.05 GHz")).not.toBeNull();
    expect(Number(slider.step)).toBe(0.05);
    expect(screen.getByText("4.25")).not.toBeNull();
    expect(screen.getByText("5.75")).not.toBeNull();
  });

  it("keeps integer-step thresholds as integers", () => {
    urlState.selectedParameter = "t1";
    renderSlider();

    expect(screen.getByText("Threshold: 100 μs")).not.toBeNull();
    expect(screen.getByText("25")).not.toBeNull();
    expect(screen.getByText("200")).not.toBeNull();
  });

  it("formats negative integer-step thresholds", () => {
    urlState.selectedParameter = "qubit_anharmonicity";
    renderSlider();

    expect(screen.getByText("Threshold: -300 MHz")).not.toBeNull();
    expect(screen.getByText("-500")).not.toBeNull();
    expect(screen.getByText("-200")).not.toBeNull();
  });

  it("shows fractional percent endpoints at the step precision", () => {
    urlState.metricsConfig = withThresholdRange("qubit_metrics", "average_gate_fidelity", {
      min: 0.9,
      max: 0.9999,
      step: 0.0001,
    });
    urlState.selectedParameter = "average_gate_fidelity";
    urlState.customThreshold = 0.9999;
    renderSlider();

    expect(screen.getByText("Threshold: 99.99%")).not.toBeNull();
    expect(screen.getByText("99.99%")).not.toBeNull();
  });

  it("shows fractional error-rate endpoints at the step precision", () => {
    urlState.metricsConfig = withThresholdRange("qubit_metrics", "average_gate_fidelity", {
      min: 0.9,
      max: 0.9999,
      step: 0.0001,
    });
    urlState.selectedParameter = "average_gate_fidelity";
    urlState.showAsErrorRate = true;
    urlState.customThreshold = 0.9999;
    const slider = renderSlider();

    expect(screen.getByText("Threshold: 0.01%")).not.toBeNull();
    expect(Number(slider.min)).toBe(0.01);
    expect(screen.getByText("0.01%")).not.toBeNull();
  });
});

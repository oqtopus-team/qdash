import { describe, it, expect } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { withNuqsTestingAdapter } from "nuqs/adapters/testing";

import { useMetricsUrlState } from "../useMetricsUrlState";

describe("useMetricsUrlState", () => {
  it("returns expected defaults when no URL params are set", () => {
    const { result } = renderHook(() => useMetricsUrlState(), {
      wrapper: withNuqsTestingAdapter({ searchParams: "" }),
    });

    expect(result.current.selectedChip).toBe("");
    expect(result.current.timeRange).toBe("7d");
    expect(result.current.selectionMode).toBe("latest");
    expect(result.current.metricType).toBe("qubit");
    expect(result.current.selectedMetric).toBe("t1");
    expect(result.current.customDays).toBeNull();
  });

  it("reads initial values from URL params", () => {
    const { result } = renderHook(() => useMetricsUrlState(), {
      wrapper: withNuqsTestingAdapter({
        searchParams:
          "chip=CHIP01&range=30d&mode=best&type=coupling&metric=t2_echo&days=14",
      }),
    });

    expect(result.current.selectedChip).toBe("CHIP01");
    expect(result.current.timeRange).toBe("30d");
    expect(result.current.selectionMode).toBe("best");
    expect(result.current.metricType).toBe("coupling");
    expect(result.current.selectedMetric).toBe("t2_echo");
    expect(result.current.customDays).toBe(14);
  });

  it("setTimeRange to 'custom' auto-sets customDays to 90 when not already set", () => {
    const { result } = renderHook(() => useMetricsUrlState(), {
      wrapper: withNuqsTestingAdapter({ searchParams: "" }),
    });

    act(() => {
      result.current.setTimeRange("custom");
    });

    expect(result.current.timeRange).toBe("custom");
    expect(result.current.customDays).toBe(90);
  });

  it("setTimeRange away from 'custom' clears customDays", () => {
    const { result } = renderHook(() => useMetricsUrlState(), {
      wrapper: withNuqsTestingAdapter({ searchParams: "range=custom&days=45" }),
    });

    expect(result.current.customDays).toBe(45);

    act(() => {
      result.current.setTimeRange("7d");
    });

    expect(result.current.timeRange).toBe("7d");
    expect(result.current.customDays).toBeNull();
  });

  it("setTimeRange to default '7d' cleans URL param", () => {
    const { result } = renderHook(() => useMetricsUrlState(), {
      wrapper: withNuqsTestingAdapter({ searchParams: "range=30d" }),
    });

    act(() => {
      result.current.setTimeRange("7d");
    });

    expect(result.current.timeRange).toBe("7d");
  });

  it("setSelectionMode to default 'latest' cleans URL param", () => {
    const { result } = renderHook(() => useMetricsUrlState(), {
      wrapper: withNuqsTestingAdapter({ searchParams: "mode=best" }),
    });

    act(() => {
      result.current.setSelectionMode("latest");
    });

    expect(result.current.selectionMode).toBe("latest");
  });

  it("setMetricType to default 'qubit' cleans URL param", () => {
    const { result } = renderHook(() => useMetricsUrlState(), {
      wrapper: withNuqsTestingAdapter({ searchParams: "type=coupling" }),
    });

    act(() => {
      result.current.setMetricType("qubit");
    });

    expect(result.current.metricType).toBe("qubit");
  });

  it("isInitialized becomes true after mount", () => {
    const { result } = renderHook(() => useMetricsUrlState(), {
      wrapper: withNuqsTestingAdapter({ searchParams: "" }),
    });

    expect(result.current.isInitialized).toBe(true);
  });
});

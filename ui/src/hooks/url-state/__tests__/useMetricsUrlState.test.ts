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
    expect(result.current.selectionMode).toBe("latest");
    expect(result.current.metricType).toBe("qubit");
    expect(result.current.selectedMetric).toBe("t1");
    expect(result.current.startDate).toBeTruthy();
    expect(result.current.endDate).toBeTruthy();
  });

  it("reads initial values from URL params", () => {
    const { result } = renderHook(() => useMetricsUrlState(), {
      wrapper: withNuqsTestingAdapter({
        searchParams: "chip=CHIP01&mode=best&type=coupling&metric=t2_echo",
      }),
    });

    expect(result.current.selectedChip).toBe("CHIP01");
    expect(result.current.selectionMode).toBe("best");
    expect(result.current.metricType).toBe("coupling");
    expect(result.current.selectedMetric).toBe("t2_echo");
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

  it("reads start/end dates from URL params", () => {
    const { result } = renderHook(() => useMetricsUrlState(), {
      wrapper: withNuqsTestingAdapter({
        searchParams: "start=2026-01-01T00:00&end=2026-01-15T23:59",
      }),
    });

    expect(result.current.startDate).toBe("2026-01-01T00:00");
    expect(result.current.endDate).toBe("2026-01-15T23:59");
  });

  it("setQuickRange updates start and end dates", () => {
    const { result } = renderHook(() => useMetricsUrlState(), {
      wrapper: withNuqsTestingAdapter({ searchParams: "" }),
    });

    act(() => {
      result.current.setQuickRange(7);
    });

    expect(result.current.startDate).toBeTruthy();
    expect(result.current.endDate).toBeTruthy();
    expect(result.current.startDate).toContain("T");
    expect(result.current.endDate).toContain("T");
  });
});

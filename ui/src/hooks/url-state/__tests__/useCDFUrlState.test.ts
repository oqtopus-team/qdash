import { describe, it, expect } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { withNuqsTestingAdapter } from "nuqs/adapters/testing";

import { useCDFUrlState } from "../useCDFUrlState";
import { URL_DEFAULTS } from "../types";

describe("useCDFUrlState", () => {
  it("returns expected defaults when no URL params are set", () => {
    const { result } = renderHook(() => useCDFUrlState(), {
      wrapper: withNuqsTestingAdapter({ searchParams: "" }),
    });

    expect(result.current.selectedChip).toBe("");
    expect(result.current.timeRange).toBe("7d");
    expect(result.current.selectionMode).toBe("latest");
    expect(result.current.selectedParameters).toEqual([...URL_DEFAULTS.CDF_PARAMETERS]);
    expect(result.current.showAsErrorRate).toBe(false);
  });

  it("reads initial values from URL params", () => {
    const { result } = renderHook(() => useCDFUrlState(), {
      wrapper: withNuqsTestingAdapter({
        searchParams: "chip=CHIP01&range=30d&mode=best&params=frequency,amplitude&errorRate=true",
      }),
    });

    expect(result.current.selectedChip).toBe("CHIP01");
    expect(result.current.timeRange).toBe("30d");
    expect(result.current.selectionMode).toBe("best");
    expect(result.current.selectedParameters).toEqual(["frequency", "amplitude"]);
    expect(result.current.showAsErrorRate).toBe(true);
  });

  it("setSelectedParameters with default values cleans URL param", () => {
    const { result } = renderHook(() => useCDFUrlState(), {
      wrapper: withNuqsTestingAdapter({
        searchParams: "params=frequency&params=amplitude",
      }),
    });

    act(() => {
      result.current.setSelectedParameters([...URL_DEFAULTS.CDF_PARAMETERS]);
    });

    // Should return defaults
    expect(result.current.selectedParameters).toEqual([...URL_DEFAULTS.CDF_PARAMETERS]);
  });

  it("setSelectedParameters with non-default values keeps them", () => {
    const { result } = renderHook(() => useCDFUrlState(), {
      wrapper: withNuqsTestingAdapter({ searchParams: "" }),
    });

    act(() => {
      result.current.setSelectedParameters(["frequency", "fidelity"]);
    });

    expect(result.current.selectedParameters).toEqual(["frequency", "fidelity"]);
  });

  it("setShowAsErrorRate with false (default) cleans URL param", () => {
    const { result } = renderHook(() => useCDFUrlState(), {
      wrapper: withNuqsTestingAdapter({ searchParams: "errorRate=true" }),
    });

    act(() => {
      result.current.setShowAsErrorRate(false);
    });

    expect(result.current.showAsErrorRate).toBe(false);
  });

  it("setShowAsErrorRate with true sets the param", () => {
    const { result } = renderHook(() => useCDFUrlState(), {
      wrapper: withNuqsTestingAdapter({ searchParams: "" }),
    });

    act(() => {
      result.current.setShowAsErrorRate(true);
    });

    expect(result.current.showAsErrorRate).toBe(true);
  });

  it("setTimeRange to default '7d' cleans URL param", () => {
    const { result } = renderHook(() => useCDFUrlState(), {
      wrapper: withNuqsTestingAdapter({ searchParams: "range=30d" }),
    });

    act(() => {
      result.current.setTimeRange("7d");
    });

    expect(result.current.timeRange).toBe("7d");
  });

  it("isInitialized becomes true after mount", () => {
    const { result } = renderHook(() => useCDFUrlState(), {
      wrapper: withNuqsTestingAdapter({ searchParams: "" }),
    });

    expect(result.current.isInitialized).toBe(true);
  });
});

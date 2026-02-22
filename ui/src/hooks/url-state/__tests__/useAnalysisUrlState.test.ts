import { describe, it, expect } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { withNuqsTestingAdapter } from "nuqs/adapters/testing";

import { useAnalysisUrlState } from "../useAnalysisUrlState";

describe("useAnalysisUrlState", () => {
  it("returns expected defaults when no URL params are set", () => {
    const { result } = renderHook(() => useAnalysisUrlState(), {
      wrapper: withNuqsTestingAdapter({ searchParams: "" }),
    });

    expect(result.current.selectedChip).toBe("");
    expect(result.current.selectedParameter).toBe("t1");
    expect(result.current.selectedParameters).toEqual([]);
    expect(result.current.selectedTag).toBe("daily");
    expect(result.current.analysisViewType).toBe("timeseries");
  });

  it("reads initial values from URL params", () => {
    const { result } = renderHook(() => useAnalysisUrlState(), {
      wrapper: withNuqsTestingAdapter({
        searchParams:
          "chip=CHIP01&parameter=t2_echo&tag=weekly&aview=correlation",
      }),
    });

    expect(result.current.selectedChip).toBe("CHIP01");
    expect(result.current.selectedParameter).toBe("t2_echo");
    expect(result.current.selectedTag).toBe("weekly");
    expect(result.current.analysisViewType).toBe("correlation");
  });

  it("reads array params from URL", () => {
    const { result } = renderHook(() => useAnalysisUrlState(), {
      wrapper: withNuqsTestingAdapter({
        searchParams: "params=t1,t2_echo",
      }),
    });

    expect(result.current.selectedParameters).toEqual(["t1", "t2_echo"]);
  });

  it("setSelectedChip updates chip value", () => {
    const { result } = renderHook(() => useAnalysisUrlState(), {
      wrapper: withNuqsTestingAdapter({ searchParams: "" }),
    });

    act(() => {
      result.current.setSelectedChip("CHIP02");
    });

    expect(result.current.selectedChip).toBe("CHIP02");
  });

  it("setSelectedChip with empty string clears to default", () => {
    const { result } = renderHook(() => useAnalysisUrlState(), {
      wrapper: withNuqsTestingAdapter({ searchParams: "chip=CHIP01" }),
    });

    act(() => {
      result.current.setSelectedChip("");
    });

    expect(result.current.selectedChip).toBe("");
  });

  it("setSelectedParameters with empty array clears to null", () => {
    const { result } = renderHook(() => useAnalysisUrlState(), {
      wrapper: withNuqsTestingAdapter({
        searchParams: "params=t1&params=t2_echo",
      }),
    });

    act(() => {
      result.current.setSelectedParameters([]);
    });

    expect(result.current.selectedParameters).toEqual([]);
  });

  it("isInitialized becomes true after mount", () => {
    const { result } = renderHook(() => useAnalysisUrlState(), {
      wrapper: withNuqsTestingAdapter({ searchParams: "" }),
    });

    expect(result.current.isInitialized).toBe(true);
  });
});

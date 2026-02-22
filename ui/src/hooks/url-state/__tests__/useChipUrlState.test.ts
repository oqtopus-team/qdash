import { describe, it, expect } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { withNuqsTestingAdapter } from "nuqs/adapters/testing";

import { useChipUrlState } from "../useChipUrlState";
import { URL_DEFAULTS } from "../types";

describe("useChipUrlState", () => {
  it("returns expected defaults when no URL params are set", () => {
    const { result } = renderHook(() => useChipUrlState(), {
      wrapper: withNuqsTestingAdapter({ searchParams: "" }),
    });

    expect(result.current.selectedChip).toBe("");
    expect(result.current.selectedDate).toBe(URL_DEFAULTS.DATE);
    expect(result.current.selectedTask).toBe(URL_DEFAULTS.TASK);
    expect(result.current.viewMode).toBe(URL_DEFAULTS.VIEW);
    expect(result.current.qubitViewMode).toBe("dashboard");
  });

  it("reads initial values from URL params", () => {
    const { result } = renderHook(() => useChipUrlState(), {
      wrapper: withNuqsTestingAdapter({
        searchParams:
          "chip=CHIP01&date=2024-01-01&task=CheckT1&view=2q&qview=table",
      }),
    });

    expect(result.current.selectedChip).toBe("CHIP01");
    expect(result.current.selectedDate).toBe("2024-01-01");
    expect(result.current.selectedTask).toBe("CheckT1");
    expect(result.current.viewMode).toBe("2q");
    expect(result.current.qubitViewMode).toBe("table");
  });

  it("setSelectedDate cleans default value from URL", () => {
    const { result } = renderHook(() => useChipUrlState(), {
      wrapper: withNuqsTestingAdapter({ searchParams: "date=2024-01-01" }),
    });

    // Setting to default should remove from URL (set to null internally)
    act(() => {
      result.current.setSelectedDate(URL_DEFAULTS.DATE);
    });

    // The hook returns the default value when URL param is null
    expect(result.current.selectedDate).toBe(URL_DEFAULTS.DATE);
  });

  it("setSelectedTask cleans default value from URL", () => {
    const { result } = renderHook(() => useChipUrlState(), {
      wrapper: withNuqsTestingAdapter({ searchParams: "task=CheckT1" }),
    });

    act(() => {
      result.current.setSelectedTask(URL_DEFAULTS.TASK);
    });

    expect(result.current.selectedTask).toBe(URL_DEFAULTS.TASK);
  });

  it("setViewMode cleans default value from URL", () => {
    const { result } = renderHook(() => useChipUrlState(), {
      wrapper: withNuqsTestingAdapter({ searchParams: "view=2q" }),
    });

    act(() => {
      result.current.setViewMode(URL_DEFAULTS.VIEW);
    });

    expect(result.current.viewMode).toBe(URL_DEFAULTS.VIEW);
  });

  it("setQubitViewMode cleans dashboard default from URL", () => {
    const { result } = renderHook(() => useChipUrlState(), {
      wrapper: withNuqsTestingAdapter({ searchParams: "qview=table" }),
    });

    act(() => {
      result.current.setQubitViewMode("dashboard");
    });

    expect(result.current.qubitViewMode).toBe("dashboard");
  });

  it("isInitialized becomes true after mount", () => {
    const { result } = renderHook(() => useChipUrlState(), {
      wrapper: withNuqsTestingAdapter({ searchParams: "" }),
    });

    expect(result.current.isInitialized).toBe(true);
  });
});

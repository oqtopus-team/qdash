import { describe, it, expect } from "vitest";
import { renderHook, act } from "@testing-library/react";
import { withNuqsTestingAdapter } from "nuqs/adapters/testing";

import { useExecutionUrlState } from "../useExecutionUrlState";

describe("useExecutionUrlState", () => {
  it("returns null default (not empty string) when no URL params are set", () => {
    const { result } = renderHook(() => useExecutionUrlState(), {
      wrapper: withNuqsTestingAdapter({ searchParams: "" }),
    });

    expect(result.current.selectedChip).toBeNull();
  });

  it("reads initial chip from URL params", () => {
    const { result } = renderHook(() => useExecutionUrlState(), {
      wrapper: withNuqsTestingAdapter({ searchParams: "chip=CHIP01" }),
    });

    expect(result.current.selectedChip).toBe("CHIP01");
  });

  it("setSelectedChip updates chip value", () => {
    const { result } = renderHook(() => useExecutionUrlState(), {
      wrapper: withNuqsTestingAdapter({ searchParams: "" }),
    });

    act(() => {
      result.current.setSelectedChip("CHIP02");
    });

    expect(result.current.selectedChip).toBe("CHIP02");
  });

  it("setSelectedChip with null removes param from URL", () => {
    const { result } = renderHook(() => useExecutionUrlState(), {
      wrapper: withNuqsTestingAdapter({ searchParams: "chip=CHIP01" }),
    });

    act(() => {
      result.current.setSelectedChip(null);
    });

    expect(result.current.selectedChip).toBeNull();
  });

  it("setSelectedChip with empty string removes param from URL", () => {
    const { result } = renderHook(() => useExecutionUrlState(), {
      wrapper: withNuqsTestingAdapter({ searchParams: "chip=CHIP01" }),
    });

    act(() => {
      result.current.setSelectedChip("");
    });

    // Empty string is converted to null by the hook (chip || null)
    expect(result.current.selectedChip).toBeNull();
  });

  it("isInitialized becomes true after mount", () => {
    const { result } = renderHook(() => useExecutionUrlState(), {
      wrapper: withNuqsTestingAdapter({ searchParams: "" }),
    });

    expect(result.current.isInitialized).toBe(true);
  });
});

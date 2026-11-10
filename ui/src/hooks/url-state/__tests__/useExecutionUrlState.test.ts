import { describe, it, expect, vi } from "vitest";
import { renderHook, act, waitFor } from "@testing-library/react";
import { withNuqsTestingAdapter } from "nuqs/adapters/testing";

import { useExecutionUrlState } from "../useExecutionUrlState";

describe("useExecutionUrlState", () => {
  it.each(["20260231", "20261301", "20260010", "20260431", "20260229", "20260100"])(
    "ignores invalid calendar day %s",
    (date) => {
      const { result } = renderHook(() => useExecutionUrlState(), {
        wrapper: withNuqsTestingAdapter({ searchParams: `date=${date}` }),
      });
      expect(result.current.selectedDate).toBe("latest");
      act(() => result.current.setSelectedDate(date));
      expect(result.current.selectedDate).toBe("latest");
    },
  );
  it("accepts a leap day", () => {
    const { result } = renderHook(() => useExecutionUrlState(), {
      wrapper: withNuqsTestingAdapter({ searchParams: "date=20240229" }),
    });
    expect(result.current.selectedDate).toBe("20240229");
  });

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

  it("reads a YYYYMMDD day filter from the date param and treats others as latest", () => {
    const day = renderHook(() => useExecutionUrlState(), {
      wrapper: withNuqsTestingAdapter({ searchParams: "chip=CHIP01&date=20261101" }),
    });
    const bogus = renderHook(() => useExecutionUrlState(), {
      wrapper: withNuqsTestingAdapter({ searchParams: "date=yesterday" }),
    });
    const none = renderHook(() => useExecutionUrlState(), {
      wrapper: withNuqsTestingAdapter({ searchParams: "" }),
    });

    expect(day.result.current.selectedDate).toBe("20261101");
    expect(bogus.result.current.selectedDate).toBe("latest");
    expect(none.result.current.selectedDate).toBe("latest");
  });

  it("writes a picked day to the URL and removes it for latest", async () => {
    const onUrlUpdate = vi.fn();
    const { result } = renderHook(() => useExecutionUrlState(), {
      wrapper: withNuqsTestingAdapter({ searchParams: "chip=CHIP01", onUrlUpdate }),
    });

    await act(async () => {
      result.current.setSelectedDate("20261101");
    });
    expect(result.current.selectedDate).toBe("20261101");
    await waitFor(() =>
      expect(onUrlUpdate.mock.lastCall?.[0].searchParams.get("date")).toBe("20261101"),
    );

    await act(async () => {
      result.current.setSelectedDate("latest");
    });
    expect(result.current.selectedDate).toBe("latest");
    await waitFor(() =>
      expect(onUrlUpdate.mock.lastCall?.[0].searchParams.has("date")).toBe(false),
    );
  });
});

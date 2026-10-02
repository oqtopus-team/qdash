import { describe, it, expect } from "vitest";
import { renderHook } from "@testing-library/react";
import { withNuqsTestingAdapter } from "nuqs/adapters/testing";

import { useRangeModeUrlState } from "../useRangeModeUrlState";

describe("useRangeModeUrlState", () => {
  it("returns expected defaults and hasUrlRange false when no URL params are set", () => {
    const { result } = renderHook(() => useRangeModeUrlState(), {
      wrapper: withNuqsTestingAdapter({ searchParams: "" }),
    });

    expect(result.current.startDate).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/);
    expect(result.current.endDate).toMatch(/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/);
    expect(result.current.hasUrlRange).toBe(false);
  });

  it("reads a valid start/end range from URL params and reports hasUrlRange true", () => {
    const { result } = renderHook(() => useRangeModeUrlState(), {
      wrapper: withNuqsTestingAdapter({
        searchParams: "start=2026-06-01T00:00&end=2026-06-08T00:00",
      }),
    });

    expect(result.current.startDate).toBe("2026-06-01T00:00");
    expect(result.current.endDate).toBe("2026-06-08T00:00");
    expect(result.current.hasUrlRange).toBe(true);
  });

  it("treats an empty ?start=&end= as having no URL range", () => {
    const { result } = renderHook(() => useRangeModeUrlState(), {
      wrapper: withNuqsTestingAdapter({ searchParams: "start=&end=" }),
    });

    expect(result.current.hasUrlRange).toBe(false);
  });

  it("treats a malformed URL range as having no URL range", () => {
    const { result } = renderHook(() => useRangeModeUrlState(), {
      wrapper: withNuqsTestingAdapter({
        searchParams: "start=2026-02-30T00:00&end=2026-03-03T00:00",
      }),
    });

    expect(result.current.hasUrlRange).toBe(false);
  });
});

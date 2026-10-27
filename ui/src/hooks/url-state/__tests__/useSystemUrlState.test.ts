import { act, renderHook } from "@testing-library/react";
import { withNuqsTestingAdapter } from "nuqs/adapters/testing";
import { describe, expect, it } from "vitest";

import { useSystemUrlState } from "../useSystemUrlState";

describe("useSystemUrlState", () => {
  it("has no System selected without the parameter", () => {
    const { result } = renderHook(() => useSystemUrlState(), {
      wrapper: withNuqsTestingAdapter({ searchParams: "" }),
    });
    expect(result.current.selectedSystemId).toBeNull();
  });

  it("reads ?system= and clears it with null or an empty string", () => {
    const { result } = renderHook(() => useSystemUrlState(), {
      wrapper: withNuqsTestingAdapter({ searchParams: "chip=144Qv3&system=144Qv3-quel3" }),
    });
    expect(result.current.selectedSystemId).toBe("144Qv3-quel3");

    act(() => result.current.setSelectedSystemId("144Qv3"));
    expect(result.current.selectedSystemId).toBe("144Qv3");

    act(() => result.current.setSelectedSystemId(""));
    expect(result.current.selectedSystemId).toBeNull();
  });
});

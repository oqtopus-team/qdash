import { act, renderHook } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { useGridViewState } from "@/hooks/useGridViewState";

describe("useGridViewState", () => {
  it("zooms into a region and returns to the full grid", () => {
    const { result } = renderHook(() => useGridViewState(true));

    act(() => result.current.changeViewMode("region"));
    act(() => result.current.zoomToRegion({ row: 1, col: 2 }));
    expect(result.current.zoomMode).toBe("region");
    expect(result.current.selectedRegion).toEqual({ row: 1, col: 2 });

    act(() => result.current.showFullGrid());
    expect(result.current.zoomMode).toBe("full");
    expect(result.current.selectedRegion).toBeNull();
    expect(result.current.viewMode).toBe("region");
  });

  it("leaves region zoom and selection when switching back to pan and zoom", () => {
    const { result } = renderHook(() => useGridViewState(true));

    act(() => {
      result.current.changeViewMode("region");
      result.current.setRegionSelectionEnabled(true);
      result.current.zoomToRegion({ row: 0, col: 1 });
    });
    act(() => result.current.changeViewMode("pan-zoom"));

    expect(result.current.viewMode).toBe("pan-zoom");
    expect(result.current.zoomMode).toBe("full");
    expect(result.current.selectedRegion).toBeNull();
    expect(result.current.regionSelectionEnabled).toBe(false);
  });

  it("keeps the locked view but leaves region zoom when the grid stops being square", () => {
    const { result, rerender } = renderHook(({ square }) => useGridViewState(square), {
      initialProps: { square: true },
    });

    act(() => {
      result.current.changeViewMode("region");
      result.current.setRegionSelectionEnabled(true);
      result.current.zoomToRegion({ row: 0, col: 0 });
    });
    rerender({ square: false });

    expect(result.current.viewMode).toBe("region");
    expect(result.current.zoomMode).toBe("full");
    expect(result.current.selectedRegion).toBeNull();
    expect(result.current.regionSelectionEnabled).toBe(false);
  });
});

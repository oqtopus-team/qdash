import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  GridRegionBackBar,
  GridTemplateRegionOverlay,
  GridViewModeSwitch,
  PositionedRegionOverlay,
} from "@/components/ui/GridViewControls";

afterEach(() => cleanup());

describe("GridViewModeSwitch", () => {
  it("offers named Zoom and Lock views and reports the chosen one", () => {
    const onValueChange = vi.fn();
    render(<GridViewModeSwitch value="pan-zoom" onValueChange={onValueChange} />);

    expect(screen.getByRole("tablist", { name: "Grid view" })).not.toBeNull();
    expect(screen.getByRole("tab", { name: "Zoom" }).getAttribute("aria-selected")).toBe("true");

    fireEvent.click(screen.getByRole("tab", { name: "Lock" }));
    expect(onValueChange).toHaveBeenCalledWith("region");
  });
});

describe("GridTemplateRegionOverlay", () => {
  it("places one button per region on grid lines and reports hover and selection", () => {
    const onHoverChange = vi.fn();
    const onSelect = vi.fn();
    render(
      <GridTemplateRegionOverlay
        numRegions={2}
        regionSize={4}
        hoveredRegion={{ row: 1, col: 0 }}
        onHoverChange={onHoverChange}
        onSelect={onSelect}
        padding={8}
        gap={2}
        cols={8}
        rows={8}
        cellSize={20}
      />,
    );
    const buttons = screen.getAllByTitle(/Zoom to region/);
    const region = screen.getByTitle("Zoom to region (1, 2)");

    expect(buttons).toHaveLength(4);
    expect(region.textContent).toBe("0,1");
    expect(region.style.gridColumn).toBe("5 / span 4");
    expect(region.style.gridRow).toBe("1 / span 4");
    expect(screen.getByTitle("Zoom to region (2, 1)").className).toContain("z-10");
    expect(region.className).not.toContain("z-10");

    fireEvent.mouseEnter(region);
    expect(onHoverChange).toHaveBeenLastCalledWith({ row: 0, col: 1 });
    fireEvent.mouseLeave(region);
    expect(onHoverChange).toHaveBeenLastCalledWith(null);
    fireEvent.click(region);
    expect(onSelect).toHaveBeenCalledWith({ row: 0, col: 1 });
  });
});

describe("PositionedRegionOverlay", () => {
  it("positions regions by cell pitch without trailing gaps", () => {
    render(
      <PositionedRegionOverlay
        numRegions={2}
        regionSize={2}
        hoveredRegion={null}
        onHoverChange={vi.fn()}
        onSelect={vi.fn()}
        cellSize={30}
        gap={4}
      />,
    );
    const region = screen.getByTitle("Zoom to region (2, 2)");

    expect(region.style.top).toBe("68px");
    expect(region.style.left).toBe("68px");
    expect(region.style.width).toBe("64px");
    expect(region.style.height).toBe("64px");
  });
});

describe("GridRegionBackBar", () => {
  it("labels the one-based region with its detail and returns to the full view", () => {
    const onBack = vi.fn();
    render(
      <GridRegionBackBar region={{ row: 0, col: 1 }} onBack={onBack} detail=" (Qubits 4 - 11)" />,
    );

    expect(screen.getByText("Region 1,2 (Qubits 4 - 11)")).not.toBeNull();
    fireEvent.click(screen.getByRole("button", { name: "← Back to Full View" }));
    expect(onBack).toHaveBeenCalledTimes(1);
  });
});

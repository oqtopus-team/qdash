import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RegionZoomToggle } from "@/components/ui/RegionZoomToggle";

describe("RegionZoomToggle", () => {
  afterEach(() => cleanup());

  it("enables region zoom once when the label is clicked", () => {
    const onToggle = vi.fn();
    render(<RegionZoomToggle enabled={false} onToggle={onToggle} />);

    fireEvent.click(screen.getByText("Region Zoom"));

    expect(onToggle).toHaveBeenCalledOnce();
    expect(onToggle).toHaveBeenCalledWith(true);
  });

  it("disables region zoom from the checkbox", () => {
    const onToggle = vi.fn();
    render(<RegionZoomToggle enabled onToggle={onToggle} />);

    const checkbox = screen.getByRole("checkbox", { name: /Region Zoom/ });
    expect((checkbox as HTMLInputElement).checked).toBe(true);

    fireEvent.click(checkbox);

    expect(onToggle).toHaveBeenCalledOnce();
    expect(onToggle).toHaveBeenCalledWith(false);
  });
});

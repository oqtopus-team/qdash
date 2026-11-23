import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { RegionZoomToggle } from "@/components/ui/RegionZoomToggle";

const DISABLED_HINT = "Enable to zoom into specific regions";
const ENABLED_HINT = "Click any region on the grid to zoom in";

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

  // jsdom has no layout, so these tests check that both states render the same
  // content; the pixel width itself must be checked in a browser.
  it("keeps the same content mounted in both states", () => {
    const { container, rerender } = render(<RegionZoomToggle enabled={false} onToggle={vi.fn()} />);
    const label = container.querySelector("label");
    const disabledText = label?.textContent;
    const disabledElementCount = label?.querySelectorAll("*").length;

    rerender(<RegionZoomToggle enabled onToggle={vi.fn()} />);

    expect(label?.textContent).toBe(disabledText);
    expect(label?.querySelectorAll("*").length).toBe(disabledElementCount);
    expect(screen.getByText(DISABLED_HINT)).toBeInTheDocument();
    expect(screen.getByText(ENABLED_HINT)).toBeInTheDocument();
    expect(screen.getByText("Active")).toBeInTheDocument();
  });

  it("exposes only the disabled hint while disabled", () => {
    render(<RegionZoomToggle enabled={false} onToggle={vi.fn()} />);

    expect(screen.getByText(DISABLED_HINT)).not.toHaveAttribute("aria-hidden");
    expect(screen.getByText(DISABLED_HINT)).not.toHaveClass("invisible");
    expect(screen.getByText(ENABLED_HINT)).toHaveAttribute("aria-hidden", "true");
    expect(screen.getByText(ENABLED_HINT)).toHaveClass("invisible");
    expect(screen.getByText("Active")).toHaveAttribute("aria-hidden", "true");
    expect(screen.getByText("Active")).toHaveClass("invisible");

    const checkbox = screen.getByRole("checkbox", { name: /Region Zoom/ });
    expect(checkbox).not.toBeChecked();
    expect(checkbox).toHaveAccessibleName(expect.stringContaining(DISABLED_HINT));
    expect(checkbox).not.toHaveAccessibleName(expect.stringContaining(ENABLED_HINT));
    expect(checkbox).not.toHaveAccessibleName(expect.stringContaining("Active"));
  });

  it("exposes only the enabled hint and badge while enabled", () => {
    render(<RegionZoomToggle enabled onToggle={vi.fn()} />);

    expect(screen.getByText(ENABLED_HINT)).not.toHaveAttribute("aria-hidden");
    expect(screen.getByText(ENABLED_HINT)).not.toHaveClass("invisible");
    expect(screen.getByText(DISABLED_HINT)).toHaveAttribute("aria-hidden", "true");
    expect(screen.getByText(DISABLED_HINT)).toHaveClass("invisible");
    expect(screen.getByText("Active")).not.toHaveAttribute("aria-hidden");
    expect(screen.getByText("Active")).not.toHaveClass("invisible");

    const checkbox = screen.getByRole("checkbox", { name: /Region Zoom/ });
    expect(checkbox).toBeChecked();
    expect(checkbox).toHaveAccessibleName(expect.stringContaining("Active"));
    expect(checkbox).toHaveAccessibleName(expect.stringContaining(ENABLED_HINT));
    expect(checkbox).not.toHaveAccessibleName(expect.stringContaining(DISABLED_HINT));
  });

  // Space toggling needs a real browser, so it is verified manually.
  it("keeps the native checkbox focusable", () => {
    render(<RegionZoomToggle enabled={false} onToggle={vi.fn()} />);

    const checkbox = screen.getByRole("checkbox", { name: /Region Zoom/ });
    checkbox.focus();

    expect(checkbox).toBe(document.activeElement);
    expect(checkbox.tabIndex).toBeGreaterThanOrEqual(0);
  });
});

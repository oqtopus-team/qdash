import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GridFullscreenButton } from "@/components/ui/GridFullscreenButton";

describe("GridFullscreenButton", () => {
  afterEach(() => cleanup());

  it("floats over the grid and toggles on click", () => {
    const onToggle = vi.fn();
    const { container } = render(<GridFullscreenButton onToggle={onToggle} />);

    const button = screen.getByRole("button", { name: "Fullscreen" });
    expect(button.getAttribute("aria-pressed")).toBe("false");
    expect(button.getAttribute("data-state")).toBe("closed");
    expect(container.querySelector(".absolute")).not.toBeNull();

    fireEvent.click(button);
    expect(onToggle).toHaveBeenCalledTimes(1);
  });

  it("switches to the exit affordance while fullscreen", () => {
    render(<GridFullscreenButton isFullscreen onToggle={vi.fn()} />);

    const button = screen.getByRole("button", { name: "Exit fullscreen" });
    expect(button.getAttribute("aria-pressed")).toBe("true");
  });
});

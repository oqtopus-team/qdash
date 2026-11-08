import { afterEach, describe, expect, it, vi } from "vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { CouplingStatusDot } from "../CouplingGrid";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("CouplingStatusDot", () => {
  it("portals the tooltip to document.body and removes it on mouse leave", () => {
    render(
      <CouplingStatusDot
        label="0_1: completed"
        className="bg-success"
        style={{ position: "absolute", left: 0, top: 0 }}
        onClick={vi.fn()}
      />
    );

    const button = screen.getByRole("button");

    vi.spyOn(button, "getBoundingClientRect").mockReturnValue({
      x: 100,
      y: 80,
      left: 100,
      top: 80,
      right: 140,
      bottom: 92,
      width: 40,
      height: 12,
      toJSON: () => ({}),
    });

    expect(screen.queryByRole("tooltip")).toBeNull();

    fireEvent.mouseEnter(button);

    const tooltip = screen.getByRole("tooltip");

    expect(tooltip.textContent).toBe("0_1: completed");
    expect(tooltip.parentElement).toBe(document.body);
    expect(tooltip.style.position).toBe("fixed");
    expect(tooltip.style.left).toBe("120px");
    expect(tooltip.style.top).toBe("72px");
    expect(tooltip.style.zIndex).toBe("9999");

    fireEvent.mouseLeave(button);

    expect(screen.queryByRole("tooltip")).toBeNull();
  });
});

import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CouplingStatusDot } from "../CouplingGrid";

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

function renderDot(onClick = vi.fn()) {
  render(
    <div data-testid="clip" style={{ overflow: "hidden" }}>
      <CouplingStatusDot
        label="0_1: completed"
        className="bg-success"
        style={{ position: "absolute", left: 0, top: 0 }}
        onClick={onClick}
      />
    </div>,
  );
  return { onClick, button: screen.getByRole("button", { name: "0_1: completed" }) };
}

describe("CouplingStatusDot", () => {
  it("shows the tooltip outside the clipping container after the delay and dismisses it", () => {
    vi.useFakeTimers();
    const { button } = renderDot();

    expect(screen.queryByRole("tooltip")).toBeNull();

    fireEvent.pointerMove(button, { pointerType: "mouse" });
    act(() => vi.advanceTimersByTime(350));

    const tooltip = screen.getByRole("tooltip");
    expect(tooltip.textContent).toBe("0_1: completed");
    expect(screen.getByTestId("clip").contains(tooltip)).toBe(false);

    fireEvent.keyDown(button, { key: "Escape" });
    expect(screen.queryByRole("tooltip")).toBeNull();
  });

  it("shows the label on keyboard focus", () => {
    const { button } = renderDot();

    act(() => button.focus());

    expect(screen.getByRole("tooltip").textContent).toBe("0_1: completed");
  });

  it("keeps its click behavior", () => {
    const { onClick, button } = renderDot();

    fireEvent.click(button);

    expect(onClick).toHaveBeenCalledTimes(1);
  });
});

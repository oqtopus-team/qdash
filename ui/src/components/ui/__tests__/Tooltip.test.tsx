import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from "@/components/ui/Tooltip";

function NeighbourTooltips({ wrap }: { wrap: (children: ReactNode) => ReactNode }) {
  return wrap(
    <>
      <Tooltip disableHoverableContent>
        <TooltipTrigger asChild>
          <button type="button">Qubit 0</button>
        </TooltipTrigger>
        <TooltipContent>Qubit 0: completed</TooltipContent>
      </Tooltip>
      <Tooltip disableHoverableContent>
        <TooltipTrigger asChild>
          <button type="button">Qubit 1</button>
        </TooltipTrigger>
        <TooltipContent>Qubit 1: failed</TooltipContent>
      </Tooltip>
    </>,
  );
}

function hover(name: string) {
  fireEvent.pointerMove(screen.getByRole("button", { name }), { pointerType: "mouse" });
}

function leave(name: string) {
  fireEvent.pointerLeave(screen.getByRole("button", { name }), { pointerType: "mouse" });
}

/** Opens Qubit 0 after the full delay, then moves straight to its neighbour. */
function moveToNeighbour() {
  hover("Qubit 0");
  act(() => vi.advanceTimersByTime(349));
  expect(screen.queryByRole("tooltip")).toBeNull();
  act(() => vi.advanceTimersByTime(1));
  expect(screen.getByRole("tooltip").textContent).toBe("Qubit 0: completed");

  leave("Qubit 0");
  hover("Qubit 1");
}

describe("Tooltip", () => {
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it("skips the open delay when moving to a neighbour under a shared provider", () => {
    vi.useFakeTimers();
    render(
      <NeighbourTooltips wrap={(children) => <TooltipProvider>{children}</TooltipProvider>} />,
    );

    moveToNeighbour();

    expect(screen.getByRole("tooltip").textContent).toBe("Qubit 1: failed");
  });

  it("keeps the full delay for a standalone tooltip outside a provider", () => {
    vi.useFakeTimers();
    render(<NeighbourTooltips wrap={(children) => children} />);

    moveToNeighbour();

    expect(screen.queryByRole("tooltip")).toBeNull();
    act(() => vi.advanceTimersByTime(350));
    expect(screen.getByRole("tooltip").textContent).toBe("Qubit 1: failed");
  });

  it("renders accessible portal content for a trigger", () => {
    render(
      <Tooltip open>
        <TooltipTrigger asChild>
          <button type="button">Zoom in</button>
        </TooltipTrigger>
        <TooltipContent className="max-w-96">Increase the grid scale</TooltipContent>
      </Tooltip>,
    );

    const trigger = screen.getByRole("button", { name: "Zoom in" });
    const tooltip = screen.getByRole("tooltip");
    expect(document.body.contains(tooltip)).toBe(true);
    expect(trigger.getAttribute("aria-describedby")).toBe(tooltip.id);
    expect(tooltip.className).toContain("max-w-96");
    expect(tooltip.className).not.toContain("max-w-72");
  });
});

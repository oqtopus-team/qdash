import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { usePanClickGuard } from "../usePanClickGuard";

const onCellClick = vi.fn();

/** Grid stand-in with a guarded cell, mirroring the TransformComponent content. */
function GuardedCell() {
  const guard = usePanClickGuard();
  return (
    <div {...guard}>
      <button type="button" onClick={() => onCellClick()}>
        cell
      </button>
    </div>
  );
}

/** Presses the cell and releases it at the given point, as a real mouse click would. */
function pressAndRelease(cell: HTMLElement, end: { clientX: number; clientY: number }) {
  fireEvent.pointerDown(cell, { clientX: 100, clientY: 100 });
  fireEvent.pointerMove(cell, end);
  fireEvent.pointerUp(cell, end);
  return fireEvent.click(cell, { ...end, detail: 1 });
}

afterEach(() => {
  cleanup();
  onCellClick.mockClear();
});

describe("usePanClickGuard", () => {
  it("passes a plain click through untouched", () => {
    render(<GuardedCell />);

    const notPrevented = pressAndRelease(screen.getByRole("button"), {
      clientX: 100,
      clientY: 100,
    });

    expect(onCellClick).toHaveBeenCalledTimes(1);
    expect(notPrevented).toBe(true);
  });

  it("passes a click with movement within the threshold", () => {
    render(<GuardedCell />);

    pressAndRelease(screen.getByRole("button"), { clientX: 103, clientY: 104 });

    expect(onCellClick).toHaveBeenCalledTimes(1);
  });

  it("suppresses the click that ends a drag beyond the threshold", () => {
    render(<GuardedCell />);

    const notPrevented = pressAndRelease(screen.getByRole("button"), {
      clientX: 140,
      clientY: 100,
    });

    expect(onCellClick).not.toHaveBeenCalled();
    expect(notPrevented).toBe(false);
  });

  it("suppresses a drag that returns to where it started", () => {
    render(<GuardedCell />);
    const cell = screen.getByRole("button");

    fireEvent.pointerDown(cell, { clientX: 100, clientY: 100 });
    fireEvent.pointerMove(cell, { clientX: 160, clientY: 100 });
    fireEvent.pointerMove(cell, { clientX: 100, clientY: 100 });
    fireEvent.click(cell, { clientX: 100, clientY: 100, detail: 1 });

    expect(onCellClick).not.toHaveBeenCalled();
  });

  it("detects a drag from the click position when no move event was seen", () => {
    render(<GuardedCell />);
    const cell = screen.getByRole("button");

    fireEvent.pointerDown(cell, { clientX: 100, clientY: 100 });
    fireEvent.click(cell, { clientX: 140, clientY: 100, detail: 1 });

    expect(onCellClick).not.toHaveBeenCalled();
  });

  it("passes the next plain click after a suppressed drag", () => {
    render(<GuardedCell />);
    const cell = screen.getByRole("button");

    pressAndRelease(cell, { clientX: 140, clientY: 100 });
    expect(onCellClick).not.toHaveBeenCalled();

    pressAndRelease(cell, { clientX: 100, clientY: 100 });
    expect(onCellClick).toHaveBeenCalledTimes(1);
  });

  it("does not let a drag released outside the content swallow a later click", () => {
    render(<GuardedCell />);
    const cell = screen.getByRole("button");

    fireEvent.pointerDown(cell, { clientX: 100, clientY: 100 });
    fireEvent.pointerMove(cell, { clientX: 140, clientY: 100 });

    fireEvent.click(cell, { clientX: 0, clientY: 0, detail: 0 });
    expect(onCellClick).toHaveBeenCalledTimes(1);

    pressAndRelease(cell, { clientX: 100, clientY: 100 });
    expect(onCellClick).toHaveBeenCalledTimes(2);
  });

  it("passes a keyboard click with no preceding press", () => {
    render(<GuardedCell />);

    fireEvent.click(screen.getByRole("button"));

    expect(onCellClick).toHaveBeenCalledTimes(1);
  });
});

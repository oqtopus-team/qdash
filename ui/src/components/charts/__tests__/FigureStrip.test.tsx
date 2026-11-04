import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FigureStrip } from "@/components/charts/FigureStrip";

function renderStrip(itemWidth = 400) {
  const utils = render(
    <FigureStrip className="h-40">
      <div role="img" aria-label="figure 1" />
      <div role="img" aria-label="figure 2" />
      <div role="img" aria-label="figure 3" />
    </FigureStrip>,
  );
  const row = screen.getByRole("img", { name: "figure 1" }).parentElement as HTMLDivElement;
  // jsdom has no layout; describe a row 500px wide holding three 400px figures.
  Object.defineProperty(row, "clientWidth", { value: 500, configurable: true });
  Object.defineProperty(row, "scrollWidth", { value: itemWidth * 3, configurable: true });
  Array.from(row.children).forEach((child, index) => {
    Object.defineProperty(child, "offsetLeft", { value: index * itemWidth, configurable: true });
    Object.defineProperty(child, "offsetWidth", { value: itemWidth, configurable: true });
  });
  row.scrollTo = vi.fn((options?: ScrollToOptions | number) => {
    row.scrollLeft = typeof options === "object" ? (options.left ?? 0) : (options ?? 0);
    fireEvent.scroll(row);
  }) as typeof row.scrollTo;
  return { ...utils, row };
}

afterEach(cleanup);

describe("FigureStrip", () => {
  it("stays a plain row when every figure fits", () => {
    const { row } = renderStrip(100);
    act(() => fireEvent.scroll(row));

    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.queryByText(/\/ 3/)).toBeNull();
  });

  it("shows the position and a next button when figures are hidden to the right", () => {
    const { row } = renderStrip();
    act(() => fireEvent.scroll(row));

    expect(screen.getByText("1 / 3")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Next figure" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Previous figure" })).toBeNull();
  });

  it("steps one figure at a time and hides the next button at the end", () => {
    const { row } = renderStrip();
    act(() => fireEvent.scroll(row));

    fireEvent.click(screen.getByRole("button", { name: "Next figure" }));
    expect(row.scrollTo).toHaveBeenCalledWith({ left: 400, behavior: "smooth" });
    expect(screen.getByText("2 / 3")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Previous figure" })).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Next figure" }));
    expect(screen.getByText("3 / 3")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Next figure" })).toBeNull();
  });

  it("counts the last figure as current once every middle has scrolled by", () => {
    const { row } = renderStrip();
    row.scrollLeft = 1150;
    act(() => fireEvent.scroll(row));

    expect(screen.getByText("3 / 3")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Previous figure" }));
    expect(row.scrollTo).toHaveBeenCalledWith({ left: 400, behavior: "smooth" });
  });
});

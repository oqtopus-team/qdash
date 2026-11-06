import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FIGURE_RETRY_DELAYS_MS, TaskFigure } from "../TaskFigure";

vi.mock("@/client/task/task", () => ({
  useGetTaskResult: () => ({ data: undefined, isLoading: false, error: null }),
}));
vi.mock("../FigureLightbox", () => ({ FigureLightbox: () => null }));

afterEach(cleanup);

describe("TaskFigure sizing", () => {
  it("keeps its height and natural width by default, for scrolling strips", () => {
    render(<TaskFigure path="/fig/a.png" qid="5" className="h-full w-auto" hideExpandButton />);
    const img = screen.getByRole("img");
    expect(img.className).toBe("h-full w-auto");
    expect(img.parentElement?.className).toContain("shrink-0");
    expect(img.parentElement?.className).toContain("inline-flex");
  });

  it("scales down to fit its box in both directions when fit is set", () => {
    render(<TaskFigure path="/fig/a.png" qid="5" fit hideExpandButton />);
    const img = screen.getByRole("img");
    expect(img.className).toContain("w-full");
    expect(img.className).toContain("h-full");
    expect(img.className).toContain("object-contain");
    const wrapper = img.parentElement?.className ?? "";
    expect(wrapper).toContain("w-full");
    expect(wrapper).toContain("min-w-0");
    expect(wrapper).not.toContain("shrink-0");
  });
});

describe("TaskFigure loading", () => {
  const url = (path: string) => `/api/executions/figure?path=${encodeURIComponent(path)}`;

  afterEach(() => {
    vi.useRealTimers();
  });

  it("reloads a figure that failed to load before reporting an error", () => {
    vi.useFakeTimers();
    render(<TaskFigure path="/fig/a.png" qid="5" hideExpandButton />);
    expect(screen.getByRole("img").getAttribute("src")).toBe(url("/fig/a.png"));

    fireEvent.error(screen.getByRole("img"));
    expect(screen.queryByRole("img")).toBeNull();
    act(() => vi.advanceTimersByTime(FIGURE_RETRY_DELAYS_MS[0]));
    expect(screen.getByRole("img").getAttribute("src")).toBe(`${url("/fig/a.png")}&retry=1`);

    fireEvent.error(screen.getByRole("img"));
    act(() => vi.advanceTimersByTime(FIGURE_RETRY_DELAYS_MS[1]));
    expect(screen.getByRole("img").getAttribute("src")).toBe(`${url("/fig/a.png")}&retry=2`);

    fireEvent.error(screen.getByRole("img"));
    expect(screen.getByRole("alert").textContent).toContain("Failed to load image");
  });

  it("shows a figure that loads on a retry", () => {
    vi.useFakeTimers();
    render(<TaskFigure path="/fig/a.png" qid="5" hideExpandButton />);
    fireEvent.error(screen.getByRole("img"));
    act(() => vi.advanceTimersByTime(FIGURE_RETRY_DELAYS_MS[0]));
    fireEvent.load(screen.getByRole("img"));
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByRole("img")).toBeTruthy();
  });

  it("retries on request after the automatic reloads", () => {
    vi.useFakeTimers();
    render(<TaskFigure path="/fig/a.png" qid="5" hideExpandButton />);
    for (const delay of FIGURE_RETRY_DELAYS_MS) {
      fireEvent.error(screen.getByRole("img"));
      act(() => vi.advanceTimersByTime(delay));
    }
    fireEvent.error(screen.getByRole("img"));
    fireEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(screen.getByRole("img").getAttribute("src")).toBe(`${url("/fig/a.png")}&retry=3`);
  });

  it("does not carry a failure over to the next figure", () => {
    vi.useFakeTimers();
    const { rerender } = render(<TaskFigure path="/fig/a.png" qid="5" hideExpandButton />);
    for (const delay of FIGURE_RETRY_DELAYS_MS) {
      fireEvent.error(screen.getByRole("img"));
      act(() => vi.advanceTimersByTime(delay));
    }
    fireEvent.error(screen.getByRole("img"));
    expect(screen.getByRole("alert")).toBeTruthy();

    rerender(<TaskFigure path="/fig/b.png" qid="6" hideExpandButton />);
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByRole("img").getAttribute("src")).toBe(url("/fig/b.png"));
  });
});

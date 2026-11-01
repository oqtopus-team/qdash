import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TaskFigure } from "../TaskFigure";

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

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FigureLightbox } from "@/components/charts/FigureLightbox";
import { TaskFigure } from "@/components/charts/TaskFigure";

// Render the dynamically imported PlotlyRenderer as a probe exposing its props.
vi.mock("next/dynamic", () => ({
  default: () =>
    function PlotlyProbe(props: { fullPath: string; sizing?: string; className?: string }) {
      return (
        <div
          data-testid="plotly-renderer"
          data-path={props.fullPath}
          data-sizing={props.sizing ?? "figure"}
          className={props.className}
        />
      );
    },
}));
vi.mock("@/client/task/task", () => ({
  useGetTaskResult: () => ({ data: undefined, isLoading: false, error: null }),
}));

const jsonUrl = (path: string) => `/api/executions/figure?path=${encodeURIComponent(path)}`;

describe("FigureLightbox", () => {
  afterEach(() => cleanup());

  it("exposes figure controls inside an accessible dialog", () => {
    render(<FigureLightbox src="/figure.png" alt="Calibration result" onClose={vi.fn()} />);

    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(screen.getByRole("img", { name: "Calibration result" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Zoom in" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Zoom out" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Reset zoom" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Close figure" })).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Switch to interactive view" })).toBeNull();
  });

  it("requests close from the labeled close action", () => {
    const onClose = vi.fn();
    render(<FigureLightbox src="/figure.png" onClose={onClose} />);

    fireEvent.click(screen.getByRole("button", { name: "Close figure" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("fits the interactive plot to a bounded panel below the controls", () => {
    render(<FigureLightbox src="/figure.png" jsonFigurePath="/fig/a.json" onClose={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Switch to interactive view" }));

    const plot = screen.getByTestId("plotly-renderer");
    expect(plot.dataset.sizing).toBe("container");
    expect(plot.dataset.path).toBe(jsonUrl("/fig/a.json"));
    expect(plot.className).toContain("h-full");
    expect(plot.className).toContain("w-full");

    // Definite bounds on all sides; the top inset clears the top-4 control row.
    const panel = screen.getByTestId("figure-lightbox-interactive");
    expect(panel).toBe(plot.parentElement);
    expect(panel.className).toContain("absolute");
    expect(panel.className).toContain("top-16");
    expect(panel.className).toMatch(/(^| )inset-x-/);
    expect(panel.className).toMatch(/(^| )bottom-/);
    expect(panel.className).toContain("overflow-hidden");

    // Pan/zoom controls only apply to the static image.
    expect(screen.queryByRole("button", { name: "Zoom in" })).toBeNull();
    expect(screen.getByRole("button", { name: "Close figure" })).toBeTruthy();
  });

  it("returns to the pan and zoom image from interactive view", () => {
    render(<FigureLightbox src="/figure.png" jsonFigurePath="/fig/a.json" onClose={vi.fn()} />);
    fireEvent.click(screen.getByRole("button", { name: "Switch to interactive view" }));
    fireEvent.click(screen.getByRole("button", { name: "Switch to static view" }));

    expect(screen.queryByTestId("plotly-renderer")).toBeNull();
    expect(screen.getByRole("img")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Zoom in" })).toBeTruthy();
  });

  it("opens the matching JSON figure from an expanded task figure", () => {
    render(
      <TaskFigure
        path={["/fig/a.png", "/fig/b.png"]}
        jsonFigurePath={["/fig/a.json", "/fig/b.json"]}
        qid="0-1"
      />,
    );
    fireEvent.click(screen.getAllByRole("button", { name: "Expand figure" })[1]);
    fireEvent.click(screen.getByRole("button", { name: "Switch to interactive view" }));

    expect(screen.getByTestId("plotly-renderer").dataset.path).toBe(jsonUrl("/fig/b.json"));
  });

  it("offers no interactive view for a task figure without a JSON figure", () => {
    render(<TaskFigure path="/fig/a.png" qid="0-1" />);
    fireEvent.click(screen.getByRole("button", { name: "Expand figure" }));

    expect(screen.getByRole("dialog")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Switch to interactive view" })).toBeNull();
  });
});

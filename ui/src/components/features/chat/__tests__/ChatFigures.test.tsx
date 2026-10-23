import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { FigureStrip, figureLabel, figureUrl, figuresInSteps } from "../ChatFigures";

afterEach(cleanup);

describe("ChatFigures", () => {
  it("collects figures from tool steps once each, in order", () => {
    expect(
      figuresInSteps([
        { kind: "thinking", text: "", startedAt: 0 },
        {
          kind: "tool",
          id: "a",
          tool: "t",
          label: "t",
          status: "done",
          startedAt: 0,
          figures: ["x.png", "y.png"],
        },
        {
          kind: "tool",
          id: "b",
          tool: "t",
          label: "t",
          status: "done",
          startedAt: 0,
          figures: ["y.png", "z.png"],
        },
        { kind: "tool", id: "c", tool: "t", label: "t", status: "done", startedAt: 0 },
      ]),
    ).toEqual(["x.png", "y.png", "z.png"]);
  });

  it("serves figures through the API and labels them by file name", () => {
    expect(figureUrl("exec/1/CheckRabi_0.png")).toBe(
      "/api/executions/figure?path=exec%2F1%2FCheckRabi_0.png",
    );
    expect(figureLabel("exec/1/CheckRabi_0.png")).toBe("CheckRabi_0");
  });

  it("shows a thumbnail per figure and opens the preview on click", () => {
    render(<FigureStrip paths={["exec/1/CheckRabi_0.png", "exec/1/CheckT1_0.png"]} />);
    expect(screen.getByText("2 figures")).toBeTruthy();
    const thumbs = screen.getAllByRole("img");
    expect(thumbs).toHaveLength(2);
    expect(thumbs[0].getAttribute("alt")).toBe("CheckRabi_0");

    fireEvent.click(screen.getByRole("button", { name: "CheckRabi_0" }));
    expect(screen.getByRole("dialog")).toBeTruthy();
  });

  it("renders nothing without figures and no header in compact mode", () => {
    const { container } = render(<FigureStrip paths={[]} />);
    expect(container.innerHTML).toBe("");
    cleanup();
    render(<FigureStrip paths={["a.png"]} compact />);
    expect(screen.queryByText(/figure/)).toBeNull();
    expect(screen.getAllByRole("img")).toHaveLength(1);
  });
});

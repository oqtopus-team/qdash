import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { QubitTile } from "../QubitTile";

describe("QubitTile", () => {
  it("shows the id as stored", () => {
    render(<QubitTile qid="12-13" />);
    expect(screen.getByText("12-13")).toBeInTheDocument();
  });

  it("renders a status dot only when a status is given", () => {
    const { container, rerender } = render(<QubitTile qid="7" />);
    expect(container.querySelectorAll("[aria-hidden]")).toHaveLength(0);
    rerender(<QubitTile qid="7" status="failed" />);
    expect(container.querySelector("[aria-hidden]")).toHaveClass("bg-error");
  });
});

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FigureLightbox } from "@/components/charts/FigureLightbox";

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
  });

  it("requests close from the labeled close action", () => {
    const onClose = vi.fn();
    render(<FigureLightbox src="/figure.png" onClose={onClose} />);

    fireEvent.click(screen.getByRole("button", { name: "Close figure" }));
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});

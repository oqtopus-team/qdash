import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { HardwareReadinessCheck } from "../HardwareReadinessCheck";

afterEach(cleanup);

describe("HardwareReadinessCheck", () => {
  it("confirms from a click on the wrapped sentence, not only on the box", () => {
    const onConfirmedChange = vi.fn();
    render(
      <HardwareReadinessCheck
        chipId="64Qv3"
        configSources={{ available: true, sources: [] }}
        confirmed={false}
        onConfirmedChange={onConfirmedChange}
      />,
    );
    const checkbox = screen.getByRole("checkbox", {
      name: "Wiring and device parameters of 64Qv3 match the connected hardware",
    });
    // The control is the label's first child, so the shared rule centers it on the first line.
    expect(checkbox.parentElement?.tagName).toBe("LABEL");
    expect(checkbox.parentElement?.className).toContain("choice-field");
    expect(checkbox.parentElement?.firstElementChild).toBe(checkbox);

    fireEvent.click(screen.getByText(/match the connected hardware/));
    expect(onConfirmedChange).toHaveBeenCalledWith(true);
  });
});

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ColorRangeSlider } from "../ColorRangeSlider";

const COLORS = ["#440154", "#21918c", "#fde724"];

function renderSlider(overrides: Partial<Parameters<typeof ColorRangeSlider>[0]> = {}) {
  const onChange = vi.fn();
  const onReset = vi.fn();
  render(
    <ColorRangeSlider
      bounds={{ min: 0, max: 200 }}
      value={{ min: 20, max: 150 }}
      isOverridden={false}
      unit="μs"
      colors={COLORS}
      onChange={onChange}
      onReset={onReset}
      {...overrides}
    />,
  );
  return { onChange, onReset };
}

describe("ColorRangeSlider", () => {
  afterEach(() => {
    cleanup();
  });

  it("moves the minimum thumb and keeps the maximum", () => {
    const { onChange } = renderSlider();
    fireEvent.change(screen.getByLabelText("Color range minimum μs"), {
      target: { value: "40" },
    });
    expect(onChange).toHaveBeenCalledWith({ min: 40, max: 150 });
  });

  it("does not let the minimum cross the maximum", () => {
    const { onChange } = renderSlider();
    fireEvent.change(screen.getByLabelText("Color range minimum μs"), {
      target: { value: "180" },
    });
    expect(onChange).toHaveBeenCalledWith({ min: 149, max: 150 });
  });

  it("clamps the maximum to the slider bounds", () => {
    const { onChange } = renderSlider();
    fireEvent.change(screen.getByLabelText("Color range maximum μs"), {
      target: { value: "500" },
    });
    expect(onChange).toHaveBeenCalledWith({ min: 20, max: 200 });
  });

  it("commits a typed value on blur", () => {
    const { onChange } = renderSlider();
    const input = screen.getByLabelText("Color range maximum value μs");
    fireEvent.change(input, { target: { value: "120" } });
    expect(onChange).not.toHaveBeenCalled();
    fireEvent.blur(input);
    expect(onChange).toHaveBeenCalledWith({ min: 20, max: 120 });
  });

  it("only enables reset once the range differs from the default", () => {
    const { onReset } = renderSlider({ isOverridden: true });
    const button = screen.getByRole("button", { name: /reset/i });
    expect(button).not.toBeDisabled();
    fireEvent.click(button);
    expect(onReset).toHaveBeenCalledTimes(1);
  });

  it("disables reset while the default range is in use", () => {
    renderSlider();
    expect(screen.getByRole("button", { name: /reset/i })).toBeDisabled();
  });
});

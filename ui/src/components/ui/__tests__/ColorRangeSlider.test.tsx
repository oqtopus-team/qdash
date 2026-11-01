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

  it("commits a typed value immediately, without waiting for blur", () => {
    const { onChange } = renderSlider();
    const input = screen.getByLabelText("Color range maximum value μs");
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "120" } });
    expect(onChange).toHaveBeenCalledWith({ min: 20, max: 120 });
  });

  it("ignores an incomplete number while typing", () => {
    const { onChange } = renderSlider();
    const input = screen.getByLabelText("Color range minimum value μs");
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "" } });
    fireEvent.change(input, { target: { value: "-" } });
    expect(onChange).not.toHaveBeenCalled();
  });

  it("keeps the typed text while focused and snaps to the committed value on blur", () => {
    const { onChange } = renderSlider();
    const input = screen.getByLabelText("Color range minimum value μs") as HTMLInputElement;
    fireEvent.focus(input);
    fireEvent.change(input, { target: { value: "180" } });
    expect(onChange).toHaveBeenCalledWith({ min: 149, max: 150 });
    expect(input.value).toBe("180");
    fireEvent.blur(input);
    expect(input.value).toBe("20");
  });

  it("follows the thumb while the field is not focused", () => {
    const { rerender } = render(
      <ColorRangeSlider
        bounds={{ min: 0, max: 200 }}
        value={{ min: 20, max: 150 }}
        isOverridden={false}
        unit="μs"
        colors={COLORS}
        onChange={() => {}}
        onReset={() => {}}
      />,
    );
    rerender(
      <ColorRangeSlider
        bounds={{ min: 0, max: 200 }}
        value={{ min: 35, max: 150 }}
        isOverridden
        unit="μs"
        colors={COLORS}
        onChange={() => {}}
        onReset={() => {}}
      />,
    );
    expect((screen.getByLabelText("Color range minimum value μs") as HTMLInputElement).value).toBe(
      "35",
    );
  });

  it("gives the number fields a coarser step than the thumbs", () => {
    renderSlider();
    const field = screen.getByLabelText("Color range minimum value μs") as HTMLInputElement;
    const thumb = screen.getByLabelText("Color range minimum μs") as HTMLInputElement;
    expect(Number(field.step)).toBeGreaterThan(Number(thumb.step));
    expect(field.step).toBe("5");
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

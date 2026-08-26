import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ChipCreationTour,
  getChipCreationTourSteps,
} from "@/components/features/chip/ChipCreationTour";

const mocks = vi.hoisted(() => ({
  driver: vi.fn(),
  drive: vi.fn(),
  destroy: vi.fn(),
  setSteps: vi.fn(),
}));

vi.mock("driver.js", () => ({ driver: mocks.driver }));

describe("ChipCreationTour", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("targets the chip action and creation form in order", () => {
    const steps = getChipCreationTourSteps();

    expect(steps).toHaveLength(5);
    expect(steps[1].element).toBe('[data-tour="create-chip"]');
    expect(steps[1].advanceOnClick).toBe(true);
    expect(steps[2].element).toBe("#chip-id-input");
    expect(steps[3].element).toBe("#topology-select");
    expect(steps[4].element).toBe('[data-tour="submit-chip"]');
  });

  it("starts from the beginning and restarts at the create action", () => {
    mocks.driver.mockReturnValue({
      drive: mocks.drive,
      destroy: mocks.destroy,
      setSteps: mocks.setSteps,
    });
    const onDismiss = vi.fn();
    const { rerender } = render(
      <ChipCreationTour active completed={false} restartKey={0} onDismiss={onDismiss} />,
    );

    expect(mocks.drive).toHaveBeenLastCalledWith(0);

    rerender(<ChipCreationTour active completed={false} restartKey={1} onDismiss={onDismiss} />);
    expect(mocks.drive).toHaveBeenLastCalledWith(1);
  });

  it("shows a completion popover after creation", () => {
    mocks.driver.mockReturnValue({
      drive: mocks.drive,
      destroy: mocks.destroy,
      setSteps: mocks.setSteps,
    });

    render(<ChipCreationTour active completed restartKey={0} onDismiss={vi.fn()} />);

    expect(mocks.setSteps).toHaveBeenCalledWith([
      expect.objectContaining({
        popover: expect.objectContaining({ title: "Chip created", doneBtnText: "Finish" }),
      }),
    ]);
    expect(mocks.drive).toHaveBeenCalledWith();
  });
});

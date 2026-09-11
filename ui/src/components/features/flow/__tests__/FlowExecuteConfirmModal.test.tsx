import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { FlowExecuteConfirmModal } from "../FlowExecuteConfirmModal";

afterEach(cleanup);

const props = {
  flowName: "calibration",
  username: "user",
  chipId: "chip-1",
  description: "",
  tags: "",
  onConfirm: vi.fn(),
  onClose: vi.fn(),
};

describe("FlowExecuteConfirmModal availability", () => {
  it("blocks a conflict appearing while confirmation is open, then allows a released target", () => {
    const onConfirm = vi.fn();
    const { rerender } = render(
      <FlowExecuteConfirmModal {...props} onConfirm={onConfirm} disabledReason={null} />,
    );
    expect(screen.getByRole("button", { name: "Execute" })).toBeEnabled();
    rerender(
      <FlowExecuteConfirmModal
        {...props}
        onConfirm={onConfirm}
        disabledReason="Another calibration is using this hardware."
      />,
    );
    const button = screen.getByRole("button", { name: "Execute" });
    expect(button).toBeDisabled();
    expect(button).toHaveAccessibleDescription("Another calibration is using this hardware.");
    fireEvent.click(button);
    expect(onConfirm).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Cancel" })).toBeEnabled();
    rerender(<FlowExecuteConfirmModal {...props} onConfirm={onConfirm} disabledReason={null} />);
    fireEvent.click(screen.getByRole("button", { name: "Execute" }));
    expect(onConfirm).toHaveBeenCalledOnce();
  });

  it.each(["Checking hardware availability…", "Unable to check hardware availability."])(
    "explains why confirmation is disabled: %s",
    (reason) => {
      render(<FlowExecuteConfirmModal {...props} disabledReason={reason} />);
      expect(screen.getByRole("button", { name: "Execute" })).toBeDisabled();
      expect(screen.getByRole("button", { name: "Execute" })).toHaveAccessibleDescription(reason);
    },
  );
});

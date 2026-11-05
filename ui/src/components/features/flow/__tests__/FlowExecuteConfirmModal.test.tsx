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

it("prefills code defaults and leaves the code in control until edited", () => {
  const onConfirm = vi.fn();
  render(
    <FlowExecuteConfirmModal
      {...props}
      disabledReason={null}
      onConfirm={onConfirm}
      targetDefaults={{ mux_ids: [1, 3], exclude_qids: ["5"] }}
    />,
  );
  expect(screen.getByRole("textbox", { name: "MUX IDs" })).toHaveValue("1, 3");
  expect(screen.getByRole("textbox", { name: "Excluded qubit IDs" })).toHaveValue("5");
  fireEvent.click(screen.getByRole("button", { name: "Execute" }));
  expect(onConfirm).toHaveBeenCalledWith(undefined);
});

it("validates edited IDs, switches target types, and can restore code defaults", () => {
  const onConfirm = vi.fn();
  render(
    <FlowExecuteConfirmModal
      {...props}
      disabledReason={null}
      onConfirm={onConfirm}
      targetDefaults={{ mux_ids: [1], exclude_qids: ["5"] }}
    />,
  );
  fireEvent.change(screen.getByRole("textbox", { name: "MUX IDs" }), { target: { value: "2, 2" } });
  expect(screen.getByRole("button", { name: "Execute" })).toBeDisabled();
  fireEvent.change(screen.getByRole("textbox", { name: "MUX IDs" }), { target: { value: "-1" } });
  expect(screen.getByRole("button", { name: "Execute" })).toBeDisabled();
  fireEvent.change(screen.getByRole("combobox", { name: "Target type" }), {
    target: { value: "qubit" },
  });
  expect(screen.getByRole("button", { name: "Execute" })).toBeDisabled();
  fireEvent.change(screen.getByRole("textbox", { name: "Qubit IDs" }), {
    target: { value: "8, 9" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Execute" }));
  expect(onConfirm).toHaveBeenLastCalledWith({ qids: ["8", "9"] });
  fireEvent.click(screen.getByRole("button", { name: "Use code defaults" }));
  expect(screen.getByRole("textbox", { name: "MUX IDs" })).toHaveValue("1");
  fireEvent.click(screen.getByRole("button", { name: "Execute" }));
  expect(onConfirm).toHaveBeenLastCalledWith(undefined);
});

it("submits explicit MUX targets even when defaults cannot be resolved", () => {
  const onConfirm = vi.fn();
  render(<FlowExecuteConfirmModal {...props} disabledReason={null} onConfirm={onConfirm} />);
  fireEvent.change(screen.getByRole("textbox", { name: "MUX IDs" }), { target: { value: "0, 2" } });
  fireEvent.change(screen.getByRole("textbox", { name: "Excluded qubit IDs" }), {
    target: { value: "1" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Execute" }));
  expect(onConfirm).toHaveBeenCalledWith({ mux_ids: [0, 2], exclude_qids: ["1"] });
});

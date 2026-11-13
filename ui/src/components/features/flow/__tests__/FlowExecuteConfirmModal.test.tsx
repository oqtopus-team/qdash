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

describe("coupling pair targets", () => {
  it("offers coupling pairs only to compatible flows", () => {
    const { unmount } = render(<FlowExecuteConfirmModal {...props} disabledReason={null} />);
    expect(screen.queryByRole("option", { name: "Coupling pairs" })).not.toBeInTheDocument();
    unmount();
    render(
      <FlowExecuteConfirmModal {...props} disabledReason={null} targetModes={["coupling_pairs"]} />,
    );
    expect(screen.queryByRole("combobox", { name: "Target type" })).not.toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Coupling pairs" })).toHaveValue("");
  });

  it("submits control-target pairs in order and keeps their direction", () => {
    const onConfirm = vi.fn();
    render(
      <FlowExecuteConfirmModal
        {...props}
        disabledReason={null}
        onConfirm={onConfirm}
        targetModes={["coupling_pairs"]}
      />,
    );
    fireEvent.change(screen.getByRole("textbox", { name: "Coupling pairs" }), {
      target: { value: " 63-85, 85-63\n64-42  39-61\n" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Execute" }));
    expect(onConfirm).toHaveBeenCalledWith({
      coupling_pairs: [
        ["63", "85"],
        ["85", "63"],
        ["64", "42"],
        ["39", "61"],
      ],
    });
  });

  it.each([
    ["63-85-1", "Use control-target pairs"],
    ["63, 85", "Use control-target pairs"],
    ["(63, 85)", "Use control-target pairs"],
    ["63-85, (64, 42)", "Use control-target pairs"],
    ["63 - 85", "Use control-target pairs"],
    ["63-x", "Use control-target pairs"],
    ["63-63", "Each pair needs two different qubits."],
    ["63-85\n63-85", "Remove duplicate coupling pairs."],
    ["  ", "Enter at least one coupling pair."],
  ])("blocks invalid pairs: %s", (value, message) => {
    const onConfirm = vi.fn();
    render(
      <FlowExecuteConfirmModal
        {...props}
        disabledReason={null}
        onConfirm={onConfirm}
        targetModes={["coupling_pairs"]}
      />,
    );
    fireEvent.change(screen.getByRole("textbox", { name: "Coupling pairs" }), {
      target: { value },
    });
    expect(screen.getByRole("alert")).toHaveTextContent(message);
    const button = screen.getByRole("button", { name: "Execute" });
    expect(button).toBeDisabled();
    fireEvent.click(button);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("prefills pair defaults and leaves the code in control until edited", () => {
    const onConfirm = vi.fn();
    render(
      <FlowExecuteConfirmModal
        {...props}
        disabledReason={null}
        onConfirm={onConfirm}
        targetModes={["coupling_pairs"]}
        targetDefaults={{
          coupling_pairs: [
            ["0", "1"],
            ["5", "4"],
          ],
        }}
      />,
    );
    const field = screen.getByRole("textbox", { name: "Coupling pairs" });
    expect(field).toHaveValue("0-1, 5-4");
    fireEvent.click(screen.getByRole("button", { name: "Execute" }));
    expect(onConfirm).toHaveBeenLastCalledWith(undefined);
    fireEvent.change(field, { target: { value: "1-0" } });
    fireEvent.click(screen.getByRole("button", { name: "Use code defaults" }));
    expect(field).toHaveValue("0-1, 5-4");
    fireEvent.click(screen.getByRole("button", { name: "Execute" }));
    expect(onConfirm).toHaveBeenLastCalledWith(undefined);
  });

  it.each([undefined, ["mux_ids", "qids"] as const])(
    "ignores pair defaults the flow cannot accept (modes: %s)",
    (targetModes) => {
      const onConfirm = vi.fn();
      render(
        <FlowExecuteConfirmModal
          {...props}
          disabledReason={null}
          onConfirm={onConfirm}
          targetModes={targetModes ? [...targetModes] : undefined}
          targetDefaults={{ coupling_pairs: [["0", "1"]] }}
        />,
      );
      expect(screen.queryByRole("textbox", { name: "Coupling pairs" })).not.toBeInTheDocument();
      expect(screen.queryByRole("option", { name: "Coupling pairs" })).not.toBeInTheDocument();
      expect(screen.getByRole("combobox", { name: "Target type" })).toHaveValue("mux");
      expect(screen.getByRole("textbox", { name: "MUX IDs" })).toHaveValue("");
      expect(screen.getByText(/Targets are dynamic, unset, or differ/)).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: "Execute" }));
      expect(onConfirm).toHaveBeenLastCalledWith(undefined);

      fireEvent.change(screen.getByRole("combobox", { name: "Target type" }), {
        target: { value: "qubit" },
      });
      fireEvent.change(screen.getByRole("textbox", { name: "Qubit IDs" }), {
        target: { value: "4" },
      });
      fireEvent.click(screen.getByRole("button", { name: "Use code defaults" }));
      expect(screen.queryByRole("textbox", { name: "Coupling pairs" })).not.toBeInTheDocument();
      expect(screen.getByRole("textbox", { name: "MUX IDs" })).toHaveValue("");
      fireEvent.click(screen.getByRole("button", { name: "Execute" }));
      expect(onConfirm).toHaveBeenLastCalledWith(undefined);
      expect(onConfirm).not.toHaveBeenCalledWith(
        expect.objectContaining({ coupling_pairs: expect.anything() }),
      );
    },
  );
});

const manualPlan = (status: "resolved" | "invalid" | "unresolved" = "resolved") => ({
  status: "ready" as const,
  plan: {
    flow_name: "calibration",
    chip_id: "chip-1",
    source_updated_at: "2026-11-01T00:00:00",
    status,
    reason: status === "unresolved" ? "the entrypoint calls helper(), which is not followed" : null,
    runs:
      status === "unresolved"
        ? []
        : [
            {
              targets: { qids: ["0", "8", "1", "9"], exclude_qids: [] },
              steps: [
                {
                  index: 1,
                  type: "CustomOneQubit",
                  name: "rabi",
                  scope: "qubit" as const,
                  execution_mode: "manual",
                  schedule: "manual" as const,
                  rounds: [
                    { number: 1, targets: ["0", "8"] },
                    { number: 2, targets: ["1", "9"] },
                  ],
                  tasks: ["CheckRabi"],
                  summary: "Runs 2 rounds in the order written.",
                  issues:
                    status === "invalid"
                      ? [{ round: 2, targets: ["1", "9"], message: "qubits share MUX 0" }]
                      : [],
                  unchecked: [],
                },
              ],
            },
          ],
    issues: [],
    has_manual_rounds: true,
    target_override_allowed: false,
    target_override_reason: "This workflow runs manual rounds.",
  },
});

describe("FlowExecuteConfirmModal tabs and execution preview", () => {
  it("switches tabs with the keyboard and keeps edited targets", () => {
    render(<FlowExecuteConfirmModal {...props} disabledReason={null} />);
    const settings = screen.getByRole("tab", { name: "Settings" });
    expect(settings).toHaveAttribute("aria-selected", "true");
    fireEvent.change(screen.getByRole("textbox", { name: "MUX IDs" }), { target: { value: "4" } });
    fireEvent.keyDown(settings, { key: "ArrowRight" });
    const preview = screen.getByRole("tab", { name: "Execution preview" });
    expect(preview).toHaveAttribute("aria-selected", "true");
    expect(preview).toHaveFocus();
    expect(screen.getByText(/Execution preview unavailable/)).toBeInTheDocument();
    fireEvent.keyDown(preview, { key: "Home" });
    expect(screen.getByRole("textbox", { name: "MUX IDs" })).toHaveValue("4");
  });

  it("shows the exact manual rounds and hides target overrides", () => {
    const onConfirm = vi.fn();
    render(
      <FlowExecuteConfirmModal
        {...props}
        disabledReason={null}
        onConfirm={onConfirm}
        targetModes={[]}
        plan={manualPlan()}
      />,
    );
    expect(screen.queryByRole("textbox", { name: "MUX IDs" })).not.toBeInTheDocument();
    expect(screen.getByText("This workflow runs manual rounds.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Execution preview" }));
    const rows = screen.getAllByRole("row");
    expect(rows.map((row) => row.textContent)).toEqual([
      "RoundQubits, in parallel",
      "10, 8",
      "21, 9",
    ]);
    expect(screen.getByText("Manual rounds · user-defined")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Execute" }));
    expect(onConfirm).toHaveBeenCalledWith(undefined);
  });

  it("disables execution for invalid manual rounds and links to the problems", () => {
    const onConfirm = vi.fn();
    render(
      <FlowExecuteConfirmModal
        {...props}
        disabledReason={null}
        onConfirm={onConfirm}
        targetModes={[]}
        plan={manualPlan("invalid")}
      />,
    );
    const execute = screen.getByRole("button", { name: "Execute" });
    expect(execute).toBeDisabled();
    expect(execute).toHaveAccessibleDescription(/Manual rounds in this workflow cannot run/);
    fireEvent.click(screen.getByRole("button", { name: "Show problems" }));
    expect(screen.getByRole("tab", { name: /Execution preview/ })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getByText("Round 2 (1, 9): qubits share MUX 0")).toBeInTheDocument();
    fireEvent.click(execute);
    expect(onConfirm).not.toHaveBeenCalled();
  });

  it("explains an unresolved plan without blocking execution", () => {
    render(
      <FlowExecuteConfirmModal
        {...props}
        disabledReason={null}
        plan={manualPlan("unresolved")}
        hasUnsavedChanges
      />,
    );
    fireEvent.click(screen.getByRole("tab", { name: "Execution preview" }));
    expect(
      screen.getByText(
        /Cannot resolve the steps before execution: the entrypoint calls helper\(\)/,
      ),
    ).toBeInTheDocument();
    expect(screen.getAllByText(/unsaved changes/).length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Execute" })).toBeEnabled();
  });

  it("shows loading and stale states", () => {
    const { rerender } = render(
      <FlowExecuteConfirmModal {...props} disabledReason={null} plan={{ status: "loading" }} />,
    );
    fireEvent.click(screen.getByRole("tab", { name: "Execution preview" }));
    expect(screen.getByText("Reading the saved workflow…")).toBeInTheDocument();
    rerender(
      <FlowExecuteConfirmModal {...props} disabledReason={null} plan={{ status: "stale" }} />,
    );
    expect(screen.getByText(/saved workflow changed after this page loaded/)).toBeInTheDocument();
  });
});

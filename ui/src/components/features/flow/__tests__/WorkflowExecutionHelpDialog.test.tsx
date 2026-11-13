import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { useState } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { WorkflowExecutionHelpDialog } from "@/components/features/flow/WorkflowExecutionHelpDialog";

const DOCS = "https://oqtopus-team.github.io/qdash/";

function Harness({ onOpenChange = vi.fn() }: { onOpenChange?: (open: boolean) => void }) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>
        Open help
      </button>
      <WorkflowExecutionHelpDialog
        open={open}
        onOpenChange={(next) => {
          onOpenChange(next);
          setOpen(next);
        }}
      />
    </>
  );
}

function openHelp() {
  fireEvent.click(screen.getByRole("button", { name: "Open help" }));
  return screen.getByRole("dialog", { name: "Execution help" });
}

describe("WorkflowExecutionHelpDialog", () => {
  afterEach(() => {
    cleanup();
  });

  it("loads no media until it is opened", () => {
    render(<Harness />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(screen.queryByRole("img")).not.toBeInTheDocument();
  });

  it("opens on the one-qubit topic with its modes, a still poster and the docs link", () => {
    render(<Harness />);
    const dialog = openHelp();

    expect(dialog).toHaveAccessibleDescription(/qubits and coupling pairs/);
    const tab = screen.getByRole("tab", { name: "1Q execution modes" });
    expect(tab).toHaveAttribute("aria-selected", "true");
    expect(tab).toHaveFocus();
    for (const mode of ["parallel_by_mux", "parallel_by_round", "sequential"]) {
      expect(screen.getByText(mode)).toBeInTheDocument();
    }
    expect(screen.getByRole("img")).toHaveAttribute(
      "src",
      "/images/execution-help/one-qubit-execution-modes-poster.png",
    );
    expect(screen.getByRole("link", { name: /Choose an execution mode/ })).toHaveAttribute(
      "href",
      `${DOCS}user-guide/creating-workflows.html#choose-an-execution-mode`,
    );
  });

  it("plays the GIF only on request and pauses back to the poster", () => {
    render(<Harness />);
    openHelp();

    expect(screen.getByRole("link", { name: /Open full size/ })).toHaveAttribute(
      "href",
      "/images/execution-help/one-qubit-execution-modes.gif",
    );
    fireEvent.click(screen.getByRole("button", { name: "Play animation" }));
    expect(screen.getByRole("img")).toHaveAttribute(
      "src",
      "/images/execution-help/one-qubit-execution-modes.gif",
    );

    fireEvent.click(screen.getByRole("button", { name: "Pause animation" }));
    expect(screen.getByRole("img")).toHaveAttribute(
      "src",
      "/images/execution-help/one-qubit-execution-modes-poster.png",
    );
  });

  it("switches to the two-qubit topic by click and by arrow keys", () => {
    render(<Harness />);
    openHelp();

    fireEvent.click(screen.getByRole("tab", { name: "2Q CR groups" }));
    expect(screen.getByRole("tabpanel")).toHaveTextContent(/runs the groups one after another/);
    expect(screen.getByRole("img")).toHaveAttribute(
      "src",
      "/images/execution-help/two-qubit-cr-schedule-poster.png",
    );
    expect(screen.getByRole("img")).toHaveAccessibleName(/max_parallel_ops 4/);
    expect(screen.getByRole("link", { name: /Schedule two-qubit calibration/ })).toHaveAttribute(
      "href",
      `${DOCS}user-guide/creating-workflows.html#schedule-two-qubit-calibration`,
    );
    expect(screen.getByRole("link", { name: /CR gate scheduler/ })).toHaveAttribute(
      "href",
      `${DOCS}developer-guide/architecture/cr-scheduler.html#conflict-graph-and-groups`,
    );

    const twoQubit = screen.getByRole("tab", { name: "2Q CR groups" });
    fireEvent.keyDown(twoQubit, { key: "ArrowRight" });
    const oneQubit = screen.getByRole("tab", { name: "1Q execution modes" });
    expect(oneQubit).toHaveAttribute("aria-selected", "true");
    expect(oneQubit).toHaveFocus();
    fireEvent.keyDown(oneQubit, { key: "End" });
    expect(twoQubit).toHaveAttribute("aria-selected", "true");
    expect(twoQubit).toHaveFocus();
  });

  it("closes on Escape and returns focus to the trigger", async () => {
    const onOpenChange = vi.fn();
    render(<Harness onOpenChange={onOpenChange} />);
    const trigger = screen.getByRole("button", { name: "Open help" });
    trigger.focus();
    const dialog = openHelp();

    fireEvent.keyDown(dialog, { key: "Escape" });

    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await waitFor(() => expect(trigger).toHaveFocus());
  });
});

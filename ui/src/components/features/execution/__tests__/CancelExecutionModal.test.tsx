import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CancelExecutionModal } from "@/components/features/execution/CancelExecutionModal";

const confirmText = "Are you sure you want to cancel this execution? This action cannot be undone.";

afterEach(() => {
  cleanup();
});

describe("CancelExecutionModal", () => {
  it("renders nothing when closed", () => {
    const { container } = render(
      <CancelExecutionModal
        isOpen={false}
        isPending={false}
        onConfirm={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    expect(container.firstChild).toBeNull();
    expect(screen.queryByText(confirmText)).toBeNull();
  });

  it("renders the confirmation content when open", () => {
    render(<CancelExecutionModal isOpen isPending={false} onConfirm={vi.fn()} onClose={vi.fn()} />);

    expect(screen.getByText(confirmText)).toBeTruthy();
    expect(screen.getByRole("button", { name: "Cancel Execution" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Close" })).toBeTruthy();
  });

  it("calls onConfirm when the confirm button is clicked", () => {
    const onConfirm = vi.fn();
    render(
      <CancelExecutionModal isOpen isPending={false} onConfirm={onConfirm} onClose={vi.fn()} />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Cancel Execution" }));

    expect(onConfirm).toHaveBeenCalledTimes(1);
  });

  it("calls onClose when the Close button is clicked", () => {
    const onClose = vi.fn();
    render(<CancelExecutionModal isOpen isPending={false} onConfirm={vi.fn()} onClose={onClose} />);

    fireEvent.click(screen.getByRole("button", { name: "Close" }));

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("calls onClose when the backdrop is clicked and not pending", () => {
    const onClose = vi.fn();
    const { container } = render(
      <CancelExecutionModal isOpen isPending={false} onConfirm={vi.fn()} onClose={onClose} />,
    );

    const backdrop = container.querySelector(".modal-backdrop");
    expect(backdrop).toBeTruthy();
    fireEvent.click(backdrop as Element);

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("disables the actions and shows a spinner while pending", () => {
    const onConfirm = vi.fn();
    const onClose = vi.fn();
    const { container } = render(
      <CancelExecutionModal isOpen isPending onConfirm={onConfirm} onClose={onClose} />,
    );

    // Both action buttons are disabled while a cancellation is in flight.
    for (const button of screen.getAllByRole("button")) {
      expect((button as HTMLButtonElement).disabled).toBe(true);
    }
    // The confirm label is replaced by a loading spinner.
    expect(container.querySelector(".loading-spinner")).toBeTruthy();

    // Backdrop clicks are ignored while pending.
    const backdrop = container.querySelector(".modal-backdrop");
    expect(backdrop).toBeTruthy();
    fireEvent.click(backdrop as Element);
    expect(onClose).not.toHaveBeenCalled();
  });
});

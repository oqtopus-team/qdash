import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ConfirmDialog } from "@/components/ui/ConfirmDialog";

describe("ConfirmDialog", () => {
  afterEach(() => cleanup());

  it("confirms or cancels the requested action", () => {
    const onConfirm = vi.fn();
    const onOpenChange = vi.fn();
    render(
      <ConfirmDialog
        open
        title="Delete schedule?"
        description="This action cannot be undone."
        confirmLabel="Delete schedule"
        onConfirm={onConfirm}
        onOpenChange={onOpenChange}
        destructive
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Delete schedule" }));
    expect(onConfirm).toHaveBeenCalledOnce();

    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("locks actions while confirmation is pending", () => {
    render(
      <ConfirmDialog
        open
        title="Delete schedule?"
        description="This action cannot be undone."
        confirmLabel="Delete schedule"
        onConfirm={vi.fn()}
        onOpenChange={vi.fn()}
        pending
        destructive
      />,
    );

    expect((screen.getByRole("button", { name: "Cancel" }) as HTMLButtonElement).disabled).toBe(
      true,
    );
    expect(
      (screen.getByRole("button", { name: "Delete schedule" }) as HTMLButtonElement).disabled,
    ).toBe(true);
  });
});

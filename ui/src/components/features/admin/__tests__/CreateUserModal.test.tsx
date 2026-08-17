import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CreateUserModal } from "@/components/features/admin/CreateUserModal";

describe("CreateUserModal", () => {
  afterEach(() => cleanup());

  it("shows an inline validation error for an empty username", async () => {
    const onSave = vi.fn();
    render(<CreateUserModal onClose={vi.fn()} onSave={onSave} isLoading={false} error={null} />);

    fireEvent.click(screen.getByRole("button", { name: "Create User" }));

    expect(await screen.findByText("Username is required")).toBeTruthy();
    expect(screen.getByPlaceholderText("Enter username").getAttribute("aria-invalid")).toBe("true");
    expect(onSave).not.toHaveBeenCalled();
  });

  it("normalizes values and displays the generated password", async () => {
    const onSave = vi.fn().mockResolvedValue("temporary-secret");
    render(<CreateUserModal onClose={vi.fn()} onSave={onSave} isLoading={false} error={null} />);

    fireEvent.change(screen.getByPlaceholderText("Enter username"), {
      target: { value: "  alice  " },
    });
    fireEvent.change(screen.getByPlaceholderText("Enter display name (optional)"), {
      target: { value: "  Alice Q.  " },
    });
    fireEvent.change(screen.getByPlaceholderText("Enter organization or affiliation (optional)"), {
      target: { value: "   " },
    });
    fireEvent.click(screen.getByRole("checkbox", { name: /Create default project/ }));
    fireEvent.click(screen.getByRole("button", { name: "Create User" }));

    await waitFor(() =>
      expect(onSave).toHaveBeenCalledWith({
        username: "alice",
        display_name: "Alice Q.",
        organization: undefined,
        create_default_project: true,
      }),
    );
    expect(await screen.findByDisplayValue("temporary-secret")).toBeTruthy();
    expect(screen.getByText("alice")).toBeTruthy();
  });
});

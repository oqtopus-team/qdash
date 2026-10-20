import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { EditUserModal } from "@/components/features/admin/EditUserModal";
import { SystemRole, type UserListItem } from "@/schemas";

const mutateAsync = vi.fn();

vi.mock("@/client/auth/auth", () => ({
  useResetPassword: () => ({ mutateAsync, isPending: false }),
}));

const baseUser: UserListItem = {
  user_id: "user-1",
  username: "alice",
  organization: "Lab",
  disabled: false,
  system_role: SystemRole.user,
  must_change_password: false,
};

/** Renders the modal with sensible defaults for tests. */
function renderModal(
  props: Partial<React.ComponentProps<typeof EditUserModal>> = {},
  user: Partial<UserListItem> = {},
) {
  const onSave = vi.fn().mockResolvedValue(undefined);
  render(
    <EditUserModal
      user={{ ...baseUser, ...user }}
      currentUsername="admin"
      onClose={vi.fn()}
      onSave={onSave}
      isLoading={false}
      {...props}
    />,
  );
  return { onSave: (props.onSave as typeof onSave | undefined) ?? onSave };
}

describe("EditUserModal", () => {
  afterEach(() => {
    cleanup();
    mutateAsync.mockReset();
  });

  it("generates and displays a one-time temporary password", async () => {
    mutateAsync.mockResolvedValue({
      data: { initial_password: "temporary-secret" },
    });
    render(
      <EditUserModal
        user={{
          user_id: "user-1",
          username: "alice",
          disabled: false,
          system_role: "user",
          must_change_password: false,
        }}
        currentUsername="admin"
        onClose={vi.fn()}
        onSave={vi.fn()}
        isLoading={false}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: "Reset Password" }));
    fireEvent.click(screen.getByRole("button", { name: "Generate and Reset" }));

    await waitFor(() => expect(mutateAsync).toHaveBeenCalledWith({ data: { username: "alice" } }));
    expect(await screen.findByDisplayValue("temporary-secret")).toBeTruthy();
    expect(screen.getByText(/shown only once/i)).toBeTruthy();
  });

  it("submits trimmed and normalized values", async () => {
    const { onSave } = renderModal();

    fireEvent.change(screen.getByLabelText("Organization"), {
      target: { value: "  New Lab  " },
    });
    fireEvent.click(screen.getByLabelText(/Account Disabled/));
    fireEvent.change(screen.getByLabelText("System Role"), {
      target: { value: "admin" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save Changes" }));

    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    expect(onSave).toHaveBeenCalledWith({
      organization: "New Lab",
      disabled: true,
      system_role: "admin",
    });
  });

  it("still submits the current system role when the select is disabled for the self user", async () => {
    const { onSave } = renderModal({ currentUsername: "alice" }, { system_role: SystemRole.admin });

    expect((screen.getByLabelText("System Role") as HTMLSelectElement).disabled).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Save Changes" }));

    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    expect(onSave).toHaveBeenCalledWith({
      organization: "Lab",
      disabled: false,
      system_role: "admin",
    });
  });

  it("shows a field error for an invalid system role and does not submit", async () => {
    const { onSave } = renderModal();
    const select = screen.getByLabelText("System Role");

    fireEvent.change(select, { target: { value: "superuser" } });
    fireEvent.click(screen.getByRole("button", { name: "Save Changes" }));

    const error = await screen.findByText("Select a system role");
    expect(select.getAttribute("aria-invalid")).toBe("true");
    expect(select.getAttribute("aria-describedby")?.split(" ")).toContain(error.id);
    expect(onSave).not.toHaveBeenCalled();
  });

  it("shows a save failure as a server error without marking fields invalid", async () => {
    const onSave = vi.fn().mockRejectedValue({ response: { data: { detail: "User not found" } } });
    renderModal({ onSave });

    fireEvent.click(screen.getByRole("button", { name: "Save Changes" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("User not found");
    expect(screen.getByLabelText("Organization").getAttribute("aria-invalid")).toBe("false");
    expect(screen.getByLabelText("System Role").getAttribute("aria-invalid")).toBe("false");
  });

  it("shows a password reset failure as an alert without submitting the form", async () => {
    mutateAsync.mockRejectedValue(new Error(""));
    const { onSave } = renderModal();

    fireEvent.click(screen.getByRole("button", { name: "Reset Password" }));
    fireEvent.click(screen.getByRole("button", { name: "Generate and Reset" }));

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("Failed to reset password");
    expect(onSave).not.toHaveBeenCalled();
  });

  it("submits an empty organization when only whitespace is entered", async () => {
    const { onSave } = renderModal();

    fireEvent.change(screen.getByLabelText("Organization"), { target: { value: "   " } });
    fireEvent.click(screen.getByRole("button", { name: "Save Changes" }));

    await waitFor(() => expect(onSave).toHaveBeenCalledTimes(1));
    expect(onSave).toHaveBeenCalledWith({
      organization: "",
      disabled: false,
      system_role: "user",
    });
  });

  it("clears the server error when saving is retried", async () => {
    const onSave = vi
      .fn()
      .mockRejectedValueOnce({ response: { data: { detail: "User not found" } } })
      .mockResolvedValueOnce(undefined);
    renderModal({ onSave });

    fireEvent.click(screen.getByRole("button", { name: "Save Changes" }));
    expect((await screen.findByRole("alert")).textContent).toContain("User not found");

    fireEvent.click(screen.getByRole("button", { name: "Save Changes" }));
    await waitFor(() => expect(screen.queryByRole("alert")).toBeNull());
    expect(onSave).toHaveBeenCalledTimes(2);
  });
});

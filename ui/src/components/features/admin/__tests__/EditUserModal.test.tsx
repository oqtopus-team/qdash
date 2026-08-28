import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { EditUserModal } from "@/components/features/admin/EditUserModal";

const mutateAsync = vi.fn();

vi.mock("@/client/auth/auth", () => ({
  useResetPassword: () => ({ mutateAsync, isPending: false }),
}));

describe("EditUserModal", () => {
  afterEach(() => {
    cleanup();
    mutateAsync.mockReset();
  });

  it("generates and displays a one-time temporary password", async () => {
    mutateAsync.mockResolvedValue({ data: { initial_password: "temporary-secret" } });
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
});

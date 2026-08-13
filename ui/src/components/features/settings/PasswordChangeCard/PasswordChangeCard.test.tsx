import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PasswordChangeCard } from "@/components/features/settings/PasswordChangeCard";

const mocks = vi.hoisted(() => ({
  mutate: vi.fn(),
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}));

vi.mock("@/client/auth/auth", () => ({
  getGetCurrentUserQueryKey: () => ["current-user"],
  useChangePassword: () => ({ mutate: mocks.mutate, isPending: false }),
}));

vi.mock("@/components/ui/Toast", () => ({ useToast: () => mocks.toast }));

describe("PasswordChangeCard", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("shows field errors instead of submitting invalid passwords", async () => {
    render(<PasswordChangeCard />);
    fireEvent.change(screen.getByPlaceholderText("Enter current password"), {
      target: { value: "current" },
    });
    fireEvent.change(screen.getByPlaceholderText("Enter new password"), {
      target: { value: "next-password" },
    });
    fireEvent.change(screen.getByPlaceholderText("Confirm new password"), {
      target: { value: "different" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Change Password" }));

    expect(await screen.findByText("New passwords do not match")).toBeTruthy();
    expect(mocks.mutate).not.toHaveBeenCalled();
  });

  it("submits validated password values", async () => {
    render(<PasswordChangeCard />);
    fireEvent.change(screen.getByPlaceholderText("Enter current password"), {
      target: { value: "current" },
    });
    fireEvent.change(screen.getByPlaceholderText("Enter new password"), {
      target: { value: "next-password" },
    });
    fireEvent.change(screen.getByPlaceholderText("Confirm new password"), {
      target: { value: "next-password" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Change Password" }));

    await waitFor(() =>
      expect(mocks.mutate).toHaveBeenCalledWith({
        data: { current_password: "current", new_password: "next-password" },
      }),
    );
  });
});

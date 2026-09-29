import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { PasswordChangeCard } from "@/components/features/settings/PasswordChangeCard";

const mocks = vi.hoisted(() => ({
  mutate: vi.fn(),
  mutationOptions: undefined as { mutation?: { onError?: (error: unknown) => void } } | undefined,
  toast: { success: vi.fn(), error: vi.fn() },
}));

vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}));

vi.mock("@/client/auth/auth", () => ({
  getGetCurrentUserQueryKey: () => ["current-user"],
  useChangePassword: (options: typeof mocks.mutationOptions) => {
    mocks.mutationOptions = options;
    return { mutate: mocks.mutate, isPending: false };
  },
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

  it("shows the server detail when the password change fails", () => {
    render(<PasswordChangeCard />);

    mocks.mutationOptions?.mutation?.onError?.(
      Object.assign(new Error("Request failed with status code 400"), {
        response: { data: { detail: "Current password is incorrect" } },
      }),
    );

    expect(mocks.toast.error).toHaveBeenCalledWith("Current password is incorrect");
  });
});

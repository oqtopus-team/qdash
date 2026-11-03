import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ProfileSettingsPanel } from "@/components/features/settings/ProfileSettingsPanel";

const mocks = vi.hoisted(() => ({
  mutate: vi.fn(),
  mutationState: { isPending: false, isError: false, error: null as unknown },
  user: { username: "alice", display_name: "Alice", avatar_key: null } as {
    username: string;
    display_name: string | null;
    avatar_key: string | null;
  },
}));

vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}));

vi.mock("@/client/auth/auth", () => ({
  getGetCurrentUserQueryKey: () => ["current-user"],
  useUpdateCurrentUserProfile: () => ({ mutate: mocks.mutate, ...mocks.mutationState }),
}));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: mocks.user }),
}));

describe("ProfileSettingsPanel", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    mocks.mutationState = { isPending: false, isError: false, error: null };
    mocks.user = { username: "alice", display_name: "Alice", avatar_key: null };
  });

  it("shows a field error instead of submitting an over-long display name", async () => {
    render(<ProfileSettingsPanel />);
    const input = screen.getByLabelText("Display name");
    fireEvent.change(input, { target: { value: "a".repeat(101) } });
    fireEvent.click(screen.getByRole("button", { name: "Save Profile" }));

    expect(await screen.findByText("Display name must be 100 characters or fewer")).toBeTruthy();
    expect(input.getAttribute("aria-invalid")).toBe("true");
    expect(input.getAttribute("aria-describedby")).toBe("profile-display-name-error");
    expect(mocks.mutate).not.toHaveBeenCalled();
  });

  it("keeps a stored avatar key that is not a preset when saving", async () => {
    mocks.user = { username: "alice", display_name: "Alice", avatar_key: "legacy" };
    render(<ProfileSettingsPanel />);
    fireEvent.change(screen.getByLabelText("Display name"), { target: { value: "Bob" } });
    fireEvent.click(screen.getByRole("button", { name: "Save Profile" }));

    await waitFor(() =>
      expect(mocks.mutate).toHaveBeenCalledWith({
        data: { display_name: "Bob", avatar_key: "legacy" },
      }),
    );
  });

  it("submits a trimmed display name and the selected avatar", async () => {
    render(<ProfileSettingsPanel />);
    fireEvent.change(screen.getByLabelText("Display name"), { target: { value: "  Bob  " } });
    fireEvent.click(screen.getByRole("button", { name: "Fox" }));
    expect(screen.getByRole("button", { name: "Fox" }).getAttribute("aria-pressed")).toBe("true");
    fireEvent.click(screen.getByRole("button", { name: "Save Profile" }));

    await waitFor(() => expect(mocks.mutate).toHaveBeenCalledTimes(1));
    expect(mocks.mutate).toHaveBeenCalledWith({
      data: { display_name: "Bob", avatar_key: "fox" },
    });
  });

  it("submits null for a cleared display name and the automatic avatar", async () => {
    mocks.user = { username: "alice", display_name: "Alice", avatar_key: "fox" };
    render(<ProfileSettingsPanel />);
    fireEvent.change(screen.getByLabelText("Display name"), { target: { value: "   " } });
    fireEvent.click(screen.getByRole("button", { name: "Automatic" }));
    fireEvent.click(screen.getByRole("button", { name: "Save Profile" }));

    await waitFor(() => expect(mocks.mutate).toHaveBeenCalledTimes(1));
    expect(mocks.mutate).toHaveBeenCalledWith({
      data: { display_name: null, avatar_key: null },
    });
  });

  it("renders the API error detail separately from field errors", () => {
    mocks.mutationState = {
      isPending: false,
      isError: true,
      error: { response: { data: { detail: "Profile is locked" } } },
    };
    render(<ProfileSettingsPanel />);

    expect(screen.getByRole("alert").textContent).toBe("Profile is locked");
    expect(screen.getByLabelText("Display name").getAttribute("aria-invalid")).toBe("false");
  });
});

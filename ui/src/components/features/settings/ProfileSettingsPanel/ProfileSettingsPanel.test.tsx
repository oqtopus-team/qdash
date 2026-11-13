import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ProfileSettingsPanel } from "@/components/features/settings/ProfileSettingsPanel";
import { glyphAvatarDataUri } from "@/lib/avatar/glyphAvatar";

const CUSTOM_SPEC = "v1:k3x9q2a-1.-2:p0w7zz:stripes:c";

const mocks = vi.hoisted(() => ({
  updateProfile: vi.fn(),
  updateAvatar: vi.fn(),
  setQueryData: vi.fn(),
  setAvatarSpec: vi.fn(),
  avatarSession: { id: "session" },
  listedSpec: null as string | null,
  profilePending: false,
  avatarError: false,
  avatar: { source: "automatic", spec: "v1:alice::solid:c" } as {
    source: "automatic" | "custom";
    spec: string;
  } | null,
  user: { username: "alice", display_name: "Alice", avatar_key: "fox" as string | null },
}));

vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries: vi.fn(), setQueryData: mocks.setQueryData }),
}));

vi.mock("@/client/auth/auth", () => ({
  getGetCurrentUserQueryKey: () => ["current-user"],
  useUpdateCurrentUserProfile: () => ({
    mutateAsync: mocks.updateProfile,
    isPending: mocks.profilePending,
  }),
}));

vi.mock("@/client/user-avatar/user-avatar", () => ({
  getGetCurrentUserAvatarQueryKey: () => ["current-user-avatar"],
  useGetCurrentUserAvatar: () => ({
    data: mocks.avatar ? { data: mocks.avatar } : undefined,
    isError: mocks.avatarError,
  }),
  useUpdateCurrentUserAvatar: () => ({ mutateAsync: mocks.updateAvatar, isPending: false }),
}));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: mocks.user }),
}));

vi.mock("@/lib/avatar/avatarSpecs", () => ({
  currentAvatarSpecSession: () => mocks.avatarSession,
  setAvatarSpec: mocks.setAvatarSpec,
  useCustomAvatarSpec: () => mocks.listedSpec,
}));

// The honeycomb needs layout and pointer input; a stand-in exposes its onChange contract.
vi.mock("@/components/ui/GlyphAvatarPicker", () => ({
  GlyphAvatarPicker: ({
    defaultValue,
    onChange,
  }: {
    defaultValue: string;
    onChange: (spec: string) => void;
  }) => (
    <div data-testid="glyph-picker" data-default={defaultValue}>
      <button type="button" onClick={() => onChange(CUSTOM_SPEC)}>
        Pick custom
      </button>
      <button type="button" onClick={() => onChange("v1:alice::solid:c")}>
        Pick automatic
      </button>
    </div>
  ),
}));

function avatarResponse(source: "automatic" | "custom", spec: string) {
  return { data: { source, spec, generator: "glyph-avatar", generator_version: "0.1.0" } };
}

function previewSrc(name: string): string | null {
  return screen.getByRole("img", { name }).getAttribute("src");
}

describe("ProfileSettingsPanel", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    mocks.profilePending = false;
    mocks.avatar = { source: "automatic", spec: "v1:alice::solid:c" };
    mocks.avatarError = false;
    mocks.listedSpec = null;
    mocks.avatarSession = { id: "session" };
    mocks.user = { username: "alice", display_name: "Alice", avatar_key: "fox" };
  });

  it("offers the glyph picker instead of emoji presets, starting at the saved spec", () => {
    render(<ProfileSettingsPanel />);
    expect(screen.getByTestId("glyph-picker").dataset.default).toBe("v1:alice::solid:c");
    for (const preset of ["Fox", "Cat", "Planet", "Automatic"]) {
      expect(screen.queryByRole("button", { name: preset })).toBeNull();
    }
    expect(screen.getByRole("button", { name: "Use automatic avatar" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Save Profile" })).toBeDisabled();
  });

  it("shows a field error instead of submitting an over-long display name", async () => {
    render(<ProfileSettingsPanel />);
    const input = screen.getByLabelText("Display name");
    fireEvent.change(input, { target: { value: "a".repeat(101) } });
    fireEvent.click(screen.getByRole("button", { name: "Save Profile" }));

    expect(await screen.findByText("Display name must be 100 characters or fewer")).toBeTruthy();
    expect(input.getAttribute("aria-invalid")).toBe("true");
    expect(input.getAttribute("aria-describedby")).toBe("profile-display-name-error");
    expect(mocks.updateProfile).not.toHaveBeenCalled();
  });

  it("saves only the display name and leaves the legacy avatar key untouched", async () => {
    mocks.updateProfile.mockResolvedValue({});
    render(<ProfileSettingsPanel />);
    fireEvent.change(screen.getByLabelText("Display name"), { target: { value: "  Bob  " } });
    fireEvent.click(screen.getByRole("button", { name: "Save Profile" }));

    await waitFor(() => expect(mocks.updateProfile).toHaveBeenCalledTimes(1));
    expect(mocks.updateProfile).toHaveBeenCalledWith({ data: { display_name: "Bob" } });
    expect(mocks.updateAvatar).not.toHaveBeenCalled();
  });

  it("previews a picked avatar locally and saves its spec with the profile", async () => {
    mocks.updateAvatar.mockResolvedValue(avatarResponse("custom", CUSTOM_SPEC));
    render(<ProfileSettingsPanel />);
    expect(previewSrc("alice")).toBe(glyphAvatarDataUri("v1:alice::solid:c"));
    fireEvent.click(screen.getByRole("button", { name: "Pick custom" }));

    expect(previewSrc("Unsaved avatar preview")).toBe(glyphAvatarDataUri(CUSTOM_SPEC));
    expect(screen.getByText("New avatar selected. Save to apply it.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Save Profile" }));

    await waitFor(() => expect(mocks.updateAvatar).toHaveBeenCalledTimes(1));
    expect(mocks.updateAvatar).toHaveBeenCalledWith({ data: { spec: CUSTOM_SPEC } });
    expect(mocks.updateProfile).not.toHaveBeenCalled();
    expect(mocks.setAvatarSpec).toHaveBeenCalledWith("alice", CUSTOM_SPEC, mocks.avatarSession);
    expect(mocks.setQueryData).toHaveBeenCalledWith(
      ["current-user-avatar"],
      avatarResponse("custom", CUSTOM_SPEC),
    );
    expect(await screen.findByText("Profile updated.")).toBeTruthy();
  });

  it("resets a custom avatar to the automatic one", async () => {
    mocks.avatar = { source: "custom", spec: CUSTOM_SPEC };
    mocks.updateAvatar.mockResolvedValue(avatarResponse("automatic", "v1:alice::solid:c"));
    render(<ProfileSettingsPanel />);
    expect(screen.getByTestId("glyph-picker").dataset.default).toBe(CUSTOM_SPEC);
    expect(previewSrc("alice")).toBe(glyphAvatarDataUri(CUSTOM_SPEC));

    fireEvent.click(screen.getByRole("button", { name: "Use automatic avatar" }));
    expect(screen.getByTestId("glyph-picker").dataset.default).toBe("v1:alice::solid:c");
    expect(screen.getByText("Automatic avatar selected. Save to apply it.")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Save Profile" }));

    await waitFor(() => expect(mocks.updateAvatar).toHaveBeenCalledTimes(1));
    expect(mocks.updateAvatar).toHaveBeenCalledWith({ data: { spec: null } });
    await waitFor(() =>
      expect(mocks.setAvatarSpec).toHaveBeenCalledWith("alice", null, mocks.avatarSession),
    );
  });

  it("ignores a save response after switching accounts", async () => {
    let finish!: (value: ReturnType<typeof avatarResponse>) => void;
    mocks.updateAvatar.mockReturnValue(new Promise((resolve) => (finish = resolve)));
    const { rerender } = render(<ProfileSettingsPanel />);
    fireEvent.click(screen.getByRole("button", { name: "Pick custom" }));
    fireEvent.click(screen.getByRole("button", { name: "Save Profile" }));
    await waitFor(() => expect(mocks.updateAvatar).toHaveBeenCalledTimes(1));

    mocks.avatarSession = { id: "new-session" };
    mocks.user = { username: "bob", display_name: "Bob", avatar_key: null };
    mocks.avatar = { source: "automatic", spec: "v1:bob::solid:c" };
    rerender(<ProfileSettingsPanel key="bob" />);
    await act(async () => finish(avatarResponse("custom", CUSTOM_SPEC)));

    expect(mocks.setQueryData).not.toHaveBeenCalled();
    expect(mocks.setAvatarSpec).not.toHaveBeenCalled();
    expect(previewSrc("bob")).toBe(glyphAvatarDataUri("v1:bob::solid:c"));
    expect(screen.queryByText("Profile updated.")).toBeNull();
  });

  it("does not start an avatar save when the session changes during a name save", async () => {
    let finish!: (value: unknown) => void;
    mocks.updateProfile.mockReturnValue(new Promise((resolve) => (finish = resolve)));
    render(<ProfileSettingsPanel />);
    fireEvent.change(screen.getByLabelText("Display name"), { target: { value: "New name" } });
    fireEvent.click(screen.getByRole("button", { name: "Pick custom" }));
    fireEvent.click(screen.getByRole("button", { name: "Save Profile" }));
    await waitFor(() => expect(mocks.updateProfile).toHaveBeenCalledTimes(1));
    mocks.avatarSession = { id: "new-session" };
    await act(async () => finish({}));

    expect(mocks.updateAvatar).not.toHaveBeenCalled();
    expect(mocks.setQueryData).not.toHaveBeenCalled();
    expect(screen.queryByText("Profile updated.")).toBeNull();
  });

  it("treats picking the automatic spec as a reset rather than a custom avatar", async () => {
    mocks.avatar = { source: "custom", spec: CUSTOM_SPEC };
    mocks.updateAvatar.mockResolvedValue(avatarResponse("automatic", "v1:alice::solid:c"));
    render(<ProfileSettingsPanel />);
    fireEvent.click(screen.getByRole("button", { name: "Pick automatic" }));
    fireEvent.click(screen.getByRole("button", { name: "Save Profile" }));

    await waitFor(() => expect(mocks.updateAvatar).toHaveBeenCalledWith({ data: { spec: null } }));
  });

  it("cancel discards the picked avatar and display name", () => {
    render(<ProfileSettingsPanel />);
    fireEvent.change(screen.getByLabelText("Display name"), { target: { value: "Bob" } });
    fireEvent.click(screen.getByRole("button", { name: "Pick custom" }));
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.getByLabelText("Display name")).toHaveValue("Alice");
    expect(screen.queryByRole("img", { name: "Unsaved avatar preview" })).toBeNull();
    expect(screen.getByRole("button", { name: "Save Profile" })).toBeDisabled();
    expect(mocks.updateAvatar).not.toHaveBeenCalled();
  });

  it("renders the API error and keeps the selection when saving fails", async () => {
    mocks.updateAvatar.mockRejectedValue({
      response: { data: { detail: "Avatar spec is invalid" } },
    });
    render(<ProfileSettingsPanel />);
    fireEvent.click(screen.getByRole("button", { name: "Pick custom" }));
    fireEvent.click(screen.getByRole("button", { name: "Save Profile" }));

    expect((await screen.findByRole("alert")).textContent).toBe("Avatar spec is invalid");
    expect(screen.getByRole("img", { name: "Unsaved avatar preview" })).toBeTruthy();
    expect(mocks.setAvatarSpec).not.toHaveBeenCalled();
  });

  it("still shows the avatar and picker when the saved settings cannot be loaded", () => {
    mocks.avatar = null;
    mocks.avatarError = true;
    render(<ProfileSettingsPanel />);

    expect(previewSrc("alice")).toBe(glyphAvatarDataUri("v1:alice::solid:c"));
    expect(screen.getByTestId("glyph-picker").dataset.default).toBe("v1:alice::solid:c");
    expect(screen.getByRole("status").textContent).toContain("could not be loaded");
  });

  it("uses the batched custom spec while the settings are unavailable", () => {
    mocks.avatar = null;
    mocks.listedSpec = CUSTOM_SPEC;
    render(<ProfileSettingsPanel />);

    expect(previewSrc("alice")).toBe(glyphAvatarDataUri(CUSTOM_SPEC));
    expect(screen.getByTestId("glyph-picker").dataset.default).toBe(CUSTOM_SPEC);
    expect(screen.getByRole("button", { name: "Use automatic avatar" })).toBeEnabled();
  });
});

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SettingsPageContent } from "@/components/features/settings/SettingsPageContent";
import { glyphAvatarDataUri, resolveAvatarSpec } from "@/lib/avatar/glyphAvatar";
import type { MemberResponse } from "@/schemas";

const mocks = vi.hoisted(() => ({
  isOwner: true,
  updateMember: vi.fn(),
  removeMember: vi.fn(),
}));

// Avatars render from the username alone; keep the custom-spec lookup off the network.
vi.mock("@/client/user-avatar/user-avatar", () => ({
  listUserAvatars: vi.fn().mockResolvedValue({ data: { avatars: [] } }),
}));

vi.mock("@/components/features/settings/AppearanceSettingsPanel", () => ({
  AppearanceSettingsPanel: () => null,
}));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: { username: "olivia" } }),
}));

vi.mock("@/contexts/ProjectContext", () => ({
  useProject: () => ({
    currentProject: { project_id: "proj-1", name: "Lab project" },
    projects: [],
    projectId: "proj-1",
    isOwner: mocks.isOwner,
    switchProject: vi.fn(),
  }),
}));

function member(username: string, role: MemberResponse["role"]): MemberResponse {
  return {
    project_id: "proj-1",
    user_id: `id-${username}`,
    username,
    role,
    status: "active",
    invited_by: null,
    last_accessed_at: null,
  };
}

vi.mock("@/client/projects/projects", () => ({
  getListProjectMembersQueryKey: (projectId: string) => ["members", projectId],
  useListProjectMembers: () => ({
    data: { data: { members: [member("olivia", "owner"), member("bob", "viewer")] } },
    isLoading: false,
  }),
  useInviteProjectMember: () => ({ mutateAsync: vi.fn(), isPending: false, error: null }),
  useUpdateProjectMember: () => ({
    mutateAsync: mocks.updateMember,
    isPending: false,
    error: null,
  }),
  useRemoveProjectMember: () => ({
    mutateAsync: mocks.removeMember,
    isPending: false,
    error: null,
  }),
}));

function renderProjectTab() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <SettingsPageContent />
    </QueryClientProvider>,
  );
  fireEvent.click(screen.getByText("Project"));
  return screen.getByRole("table");
}

function memberRow(table: HTMLElement, username: string): HTMLElement {
  return within(table).getByText(username).closest("tr") as HTMLElement;
}

function expectAvatar(row: HTMLElement, username: string) {
  const avatar = within(row).getByRole("img", { name: username });
  expect(avatar.getAttribute("src")).toBe(glyphAvatarDataUri(resolveAvatarSpec(username, null)));
}

describe("Settings project members avatars", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    mocks.isOwner = true;
  });

  it("shows each member's avatar beside the username", () => {
    const table = renderProjectTab();

    expectAvatar(memberRow(table, "olivia"), "olivia");
    expectAvatar(memberRow(table, "bob"), "bob");
  });

  it("keeps owner role change and removal controls on member rows", async () => {
    mocks.updateMember.mockResolvedValue(undefined);
    mocks.removeMember.mockResolvedValue(undefined);
    const table = renderProjectTab();
    const bobRow = memberRow(table, "bob");

    fireEvent.change(within(bobRow).getByRole("combobox"), { target: { value: "editor" } });
    await waitFor(() =>
      expect(mocks.updateMember).toHaveBeenCalledWith({
        projectId: "proj-1",
        username: "bob",
        data: { role: "editor" },
      }),
    );

    fireEvent.click(within(bobRow).getByRole("button", { name: "Remove" }));
    await waitFor(() =>
      expect(mocks.removeMember).toHaveBeenCalledWith({ projectId: "proj-1", username: "bob" }),
    );
  });

  it("shows avatars to members without owner controls", () => {
    mocks.isOwner = false;
    const table = renderProjectTab();
    const bobRow = memberRow(table, "bob");

    expectAvatar(bobRow, "bob");
    expect(within(bobRow).queryByRole("button", { name: "Remove" })).toBeNull();
  });
});

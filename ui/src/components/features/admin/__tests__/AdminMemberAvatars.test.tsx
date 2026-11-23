import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { AdminPageContent } from "@/components/features/admin/AdminPageContent";
import { AdminUsersPanel } from "@/components/features/admin/AdminUsersPanel";
import { glyphAvatarDataUri, resolveAvatarSpec } from "@/lib/avatar/glyphAvatar";
import { SystemRole, type MemberItem, type ProjectListItem, type UserListItem } from "@/schemas";

const admin = vi.hoisted(() => ({
  addMember: vi.fn(),
  removeMember: vi.fn(),
  refetchMembers: vi.fn(),
  users: [] as unknown[],
  projects: [] as unknown[],
  members: [] as unknown[],
}));

// Avatars render from the username alone; keep the custom-spec lookup off the network.
vi.mock("@/client/user-avatar/user-avatar", () => ({
  listUserAvatars: vi.fn().mockResolvedValue({ data: { avatars: [] } }),
}));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: { username: "root", system_role: "admin" } }),
}));

vi.mock("@/client/auth/auth", () => ({
  useRegisterUser: () => ({ mutateAsync: vi.fn(), isPending: false, error: null }),
}));

vi.mock("@/client/admin/admin", () => {
  const idleMutation = () => ({ mutateAsync: vi.fn(), isPending: false, error: null });
  return {
    useListAllUsers: () => ({
      data: { data: { users: admin.users } },
      isLoading: false,
      error: null,
    }),
    useListAllProjects: () => ({
      data: { data: { projects: admin.projects } },
      isLoading: false,
      error: null,
    }),
    useListProjectMembersAdmin: () => ({
      data: { data: { members: admin.members } },
      isLoading: false,
      refetch: admin.refetchMembers,
    }),
    useAddProjectMemberAdmin: () => ({
      mutateAsync: admin.addMember,
      isPending: false,
      error: null,
    }),
    useRemoveProjectMemberAdmin: () => ({
      mutateAsync: admin.removeMember,
      isPending: false,
      error: null,
    }),
    useUpdateUserSettings: idleMutation,
    useDeleteUser: idleMutation,
    useCreateProjectForUser: idleMutation,
    useBulkImportUsers: idleMutation,
    useAdminDeleteProject: idleMutation,
    getListAllUsersQueryKey: () => ["admin-users"],
    getListAllProjectsQueryKey: () => ["admin-projects"],
  };
});

function user(username: string, overrides: Partial<UserListItem> = {}): UserListItem {
  return {
    user_id: `id-${username}`,
    username,
    display_name: `${username} display`,
    organization: "Lab",
    disabled: false,
    system_role: SystemRole.user,
    ...overrides,
  };
}

function expectAvatar(container: HTMLElement, username: string) {
  const avatar = within(container).getByRole("img", { name: username });
  expect(avatar.getAttribute("src")).toBe(glyphAvatarDataUri(resolveAvatarSpec(username, null)));
}

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("AdminUsersPanel avatars", () => {
  function renderPanel() {
    const users = [user("root", { system_role: SystemRole.admin }), user("alice")];
    const handlers = {
      onToggleUserSelection: vi.fn(),
      onEditUser: vi.fn(),
      onDeleteUser: vi.fn(),
    };
    render(
      <AdminUsersPanel
        users={users}
        filteredUsers={users}
        selectedUsers={[]}
        selectedUsernames={[]}
        bulkProjectCandidates={[]}
        userSearch=""
        userRoleFilter="all"
        userProjectFilter="all"
        currentUsername="root"
        allSelectableUsersSelected={false}
        selectableFilteredUsersCount={1}
        bulkAction={null}
        isCreatingProject={false}
        onSearchChange={vi.fn()}
        onRoleFilterChange={vi.fn()}
        onProjectFilterChange={vi.fn()}
        onOpenBulkImport={vi.fn()}
        onOpenCreateUser={vi.fn()}
        onSetBulkDeleteTargets={vi.fn()}
        onBulkCreateProjects={vi.fn()}
        onOpenAssignProject={vi.fn()}
        onClearSelection={vi.fn()}
        onToggleSelectAll={vi.fn()}
        onCreateProject={vi.fn()}
        {...handlers}
      />,
    );
    return { users, handlers };
  }

  it("shows each user's avatar beside the username in the table and keeps row actions", () => {
    const { users, handlers } = renderPanel();
    const table = screen.getByRole("table");
    const aliceRow = within(table).getByText("alice").closest("tr") as HTMLElement;

    expectAvatar(aliceRow, "alice");
    expectAvatar(within(table).getByText("root").closest("tr") as HTMLElement, "root");
    expect(within(aliceRow).getByText("alice display")).toBeTruthy();

    fireEvent.click(within(aliceRow).getByRole("checkbox"));
    fireEvent.click(within(aliceRow).getByRole("button", { name: "Edit" }));
    fireEvent.click(within(aliceRow).getByRole("button", { name: "Delete" }));
    expect(handlers.onToggleUserSelection).toHaveBeenCalledWith("alice");
    expect(handlers.onEditUser).toHaveBeenCalledWith(users[1]);
    expect(handlers.onDeleteUser).toHaveBeenCalledWith(users[1]);
  });

  it("shows avatars in the mobile user cards", () => {
    renderPanel();
    const aliceHeading = screen.getByRole("heading", { name: "alice" });
    const card = aliceHeading.closest(".card") as HTMLElement;

    expectAvatar(card, "alice");
    expect(within(card).getByRole("checkbox")).toBeTruthy();
  });
});

describe("Admin project members modal avatars", () => {
  const project: ProjectListItem = {
    project_id: "proj-1",
    name: "Lab project",
    owner_user_id: "id-owner",
    owner_username: "olivia",
    member_count: 2,
  };

  async function openMembersModal() {
    admin.users = [user("olivia"), user("bob"), user("carol")];
    admin.projects = [project];
    admin.members = [
      { user_id: "id-owner", username: "olivia", role: "owner" },
      { user_id: "id-bob", username: "bob", display_name: "Bob B", role: "viewer" },
    ] satisfies MemberItem[];
    admin.addMember.mockResolvedValue(undefined);
    admin.removeMember.mockResolvedValue(undefined);

    render(
      <QueryClientProvider client={new QueryClient()}>
        <AdminPageContent />
      </QueryClientProvider>,
    );
    fireEvent.click(screen.getByRole("tab", { name: /projects/i }));
    fireEvent.click(screen.getAllByRole("button", { name: "Members" })[0]);
    return screen.findByRole("dialog");
  }

  it("shows avatars for current members and keeps member removal", async () => {
    const dialog = await openMembersModal();
    const membersTable = within(dialog).getByRole("table");
    const bobRow = within(membersTable).getByText("bob").closest("tr") as HTMLElement;

    expectAvatar(bobRow, "bob");
    expectAvatar(within(membersTable).getByText("olivia").closest("tr") as HTMLElement, "olivia");
    expect(within(bobRow).getByText("Bob B")).toBeTruthy();

    fireEvent.click(within(bobRow).getByRole("button", { name: "Remove" }));
    await waitFor(() =>
      expect(admin.removeMember).toHaveBeenCalledWith({ projectId: "proj-1", username: "bob" }),
    );
  });

  it("shows avatars for add-member candidates and keeps selection with role", async () => {
    const dialog = await openMembersModal();
    const candidate = within(dialog).getByRole("listitem");

    expectAvatar(candidate, "carol");
    fireEvent.click(within(candidate).getByRole("checkbox"));
    fireEvent.change(within(dialog).getByRole("combobox", { name: "Role for new members" }), {
      target: { value: "editor" },
    });
    fireEvent.click(within(dialog).getByRole("button", { name: "Add Selected" }));

    await waitFor(() =>
      expect(admin.addMember).toHaveBeenCalledWith({
        projectId: "proj-1",
        data: { username: "carol", role: "editor" },
      }),
    );
  });
});

import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ForumPageContent } from "../ForumPageContent";

const mocks = vi.hoisted(() => ({
  replace: vi.fn(),
  params: new URLSearchParams(),
  listParams: [] as Array<{ status?: string | null }>,
  isLoading: false,
  mutation: () => ({ mutate: () => {}, mutateAsync: async () => {}, isPending: false }),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: mocks.replace }),
  useSearchParams: () => mocks.params,
}));

vi.mock("@tanstack/react-query", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@tanstack/react-query")>()),
  useQueryClient: () => ({ invalidateQueries: vi.fn() }),
}));

vi.mock("@/client/forum/forum", () => ({
  getGetForumPostQueryKey: () => ["forum-post"],
  getListForumCategoriesQueryKey: () => ["forum-categories"],
  getListForumPostsQueryKey: () => ["forum-posts"],
  useCreateForumCategory: mocks.mutation,
  useDeleteForumCategory: mocks.mutation,
  useUpdateForumPost: mocks.mutation,
  useGetForumPost: () => ({ data: undefined, isLoading: false }),
  useGetForumPostReplies: () => ({ data: undefined, isLoading: false }),
  useListForumCategories: () => ({ data: undefined }),
  useListForumPosts: (params: { status?: string | null }) => {
    mocks.listParams.push(params);
    return {
      data: mocks.isLoading ? undefined : { data: { posts: [], total: 7 } },
      isLoading: mocks.isLoading,
      isError: false,
      refetch: vi.fn(),
    };
  },
}));
vi.mock("@/client/chip/chip", () => ({ useListChips: () => ({ data: undefined }) }));
vi.mock("@/client/cooldown/cooldown", () => ({ useListCooldowns: () => ({ data: undefined }) }));
vi.mock("@/client/projects/projects", () => ({
  useListProjectMembers: () => ({ data: undefined }),
}));
vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: { username: "alice" } }),
}));
vi.mock("@/contexts/ProjectContext", () => ({
  useProject: () => ({ canEdit: true, isOwner: false, projectId: "p1" }),
}));
vi.mock("@/hooks/useForumLabels", () => ({ useForumLabels: () => ({ labels: [] }) }));

describe("ForumPageContent status switch", () => {
  beforeEach(() => {
    mocks.replace.mockReset();
    mocks.params = new URLSearchParams();
    mocks.listParams = [];
    mocks.isLoading = false;
  });
  afterEach(() => cleanup());

  it("shows the total only on the selected status and filters by the clicked status", () => {
    render(<ForumPageContent />);

    const tablist = screen.getByRole("tablist", { name: "Forum status" });
    expect(tablist.classList.contains("tabs-boxed")).toBe(true);
    const selected = screen.getByRole("tab", { selected: true });
    expect(selected.textContent).toBe("Open7");
    expect(screen.getByRole("tab", { name: "Resolved" }).querySelector(".badge")).toBeNull();

    fireEvent.click(screen.getByRole("tab", { name: "Resolved" }));

    expect(screen.getByRole("tab", { selected: true }).textContent).toBe("Resolved7");
    expect(mocks.listParams[mocks.listParams.length - 1]?.status).toBe("resolved");
    expect(mocks.replace).toHaveBeenLastCalledWith("/forum?forum_status=resolved", {
      scroll: false,
    });
  });

  it("selects All from the URL and clears the status filter", () => {
    mocks.params = new URLSearchParams("forum_status=all");
    render(<ForumPageContent />);

    expect(screen.getByRole("tab", { selected: true }).textContent).toBe("All7");
    expect(mocks.listParams[mocks.listParams.length - 1]?.status).toBeNull();
  });

  it("hides the count badge while the list loads", () => {
    mocks.isLoading = true;
    render(<ForumPageContent />);

    expect(screen.getByRole("tab", { selected: true }).textContent).toBe("Open");
  });
});

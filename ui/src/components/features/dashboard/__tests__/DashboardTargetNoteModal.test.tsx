import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { DashboardTargetNoteModal } from "@/components/features/dashboard/DashboardTargetNoteModal";

vi.mock("next/link", () => ({
  default: ({
    children,
    href,
    className,
  }: {
    children: React.ReactNode;
    href: string;
    className?: string;
  }) => (
    <a href={href} className={className}>
      {children}
    </a>
  ),
}));

vi.mock("@/client/forum/forum", () => ({
  useListForumPosts: () => ({
    data: { data: { posts: [] } },
  }),
}));

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

const noteMutations = vi.hoisted(() => ({
  createQubitComment: vi.fn(),
  updateQubitComment: vi.fn(),
  deleteQubitComment: vi.fn(),
}));

vi.mock("@/client/note/note", () => ({
  getGetChipNotesSummaryQueryKey: () => ["chip-notes-summary"],
  useCreateCouplingNoteComment: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useCreateQubitNoteComment: () => ({
    isPending: false,
    mutateAsync: noteMutations.createQubitComment,
  }),
  useDeleteCouplingNote: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useDeleteCouplingNoteComment: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useDeleteQubitNote: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useDeleteQubitNoteComment: () => ({
    isPending: false,
    mutateAsync: noteMutations.deleteQubitComment,
  }),
  useUpdateCouplingNoteComment: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useUpdateQubitNoteComment: () => ({
    isPending: false,
    mutateAsync: noteMutations.updateQubitComment,
  }),
  useUpsertCouplingNote: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useUpsertQubitNote: () => ({ isPending: false, mutateAsync: vi.fn() }),
}));

function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
}

function renderModal(props?: Partial<React.ComponentProps<typeof DashboardTargetNoteModal>>) {
  const queryClient = createQueryClient();
  const onClose = props?.onClose ?? vi.fn();

  render(
    <QueryClientProvider client={queryClient}>
      <DashboardTargetNoteModal
        chipId="chip-1"
        targetId="0"
        currentUsername="tester"
        currentSystemRole="user"
        existing={{
          targetId: "0",
          content: "",
          username: "tester",
          updatedAt: "",
          comments: [
            {
              comment_id: "entry-1",
              content: "Current note",
              created_by: "tester",
              created_at: "2026-07-09T00:00:00Z",
              updated_by: "",
              updated_at: null,
            },
          ],
        }}
        onClose={onClose}
        {...props}
      />
    </QueryClientProvider>,
  );

  return { onClose };
}

describe("DashboardTargetNoteModal", () => {
  it("keeps the modal open when an entry edit backdrop is clicked", () => {
    const { onClose } = renderModal();

    fireEvent.click(screen.getByRole("button", { name: "Edit entry" }));
    fireEvent.click(document.querySelector(".modal") as HTMLElement);

    expect(onClose).not.toHaveBeenCalled();
  });

  it("does not reset an in-progress edit when existing note props refresh", () => {
    const queryClient = createQueryClient();
    const onClose = vi.fn();
    const initialProps = {
      chipId: "chip-1",
      targetId: "0",
      currentUsername: "tester",
      currentSystemRole: "user" as const,
      existing: {
        targetId: "0",
        content: "",
        username: "tester",
        updatedAt: "",
        comments: [
          {
            comment_id: "entry-1",
            content: "Current note",
            created_by: "tester",
            created_at: "2026-07-09T00:00:00Z",
            updated_by: "",
            updated_at: null,
          },
        ],
      },
      onClose,
    };
    const { rerender } = render(
      <QueryClientProvider client={queryClient}>
        <DashboardTargetNoteModal {...initialProps} />
      </QueryClientProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Edit entry" }));
    fireEvent.change(screen.getByDisplayValue("Current note"), {
      target: { value: "Unsaved draft" },
    });

    rerender(
      <QueryClientProvider client={queryClient}>
        <DashboardTargetNoteModal
          {...initialProps}
          existing={{
            targetId: "0",
            content: "",
            username: "tester",
            updatedAt: "2026-07-09T00:00:00Z",
            comments: [
              {
                comment_id: "entry-1",
                content: "Server refresh",
                created_by: "tester",
                created_at: "2026-07-09T00:00:00Z",
                updated_by: "tester",
                updated_at: "2026-07-09T00:00:00Z",
              },
            ],
          }}
        />
      </QueryClientProvider>,
    );

    expect(screen.getByDisplayValue("Unsaved draft")).toBeTruthy();
  });

  it("renders note entries with authors and posts without closing the modal", async () => {
    noteMutations.createQubitComment.mockResolvedValue({});
    const onClose = vi.fn();

    renderModal({
      onClose,
      existing: {
        targetId: "0",
        content: "",
        username: "",
        updatedAt: "",
        comments: [
          {
            comment_id: "entry-1",
            content: "First observation",
            created_by: "alice",
            created_at: "2026-07-09T00:00:00Z",
            updated_by: "",
            updated_at: null,
          },
        ],
      },
    });

    expect(screen.getByText("alice")).toBeTruthy();
    expect(screen.getByText("First observation")).toBeTruthy();

    fireEvent.change(screen.getByPlaceholderText("Post a target-level summary note entry..."), {
      target: { value: "Second observation" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Post" }));

    await waitFor(() => {
      expect(noteMutations.createQubitComment).toHaveBeenCalledWith({
        chipId: "chip-1",
        qid: "0",
        data: { content: "Second observation" },
        params: undefined,
      });
    });
    expect(onClose).not.toHaveBeenCalled();
  });
});

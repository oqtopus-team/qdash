import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
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
});

vi.mock("@/client/note/note", () => ({
  getGetChipNotesSummaryQueryKey: () => ["chip-notes-summary"],
  useDeleteCouplingNote: () => ({ isPending: false, mutateAsync: vi.fn() }),
  useDeleteQubitNote: () => ({ isPending: false, mutateAsync: vi.fn() }),
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
        existing={{ targetId: "0", content: "Current note", username: "tester", updatedAt: "" }}
        onClose={onClose}
        {...props}
      />
    </QueryClientProvider>,
  );

  return { onClose };
}

describe("DashboardTargetNoteModal", () => {
  it("keeps the modal open when the edit backdrop is clicked", () => {
    const { onClose } = renderModal();

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.click(document.querySelector(".modal") as HTMLElement);

    expect(onClose).not.toHaveBeenCalled();
  });

  it("does not reset an in-progress edit when existing note props refresh", () => {
    const queryClient = createQueryClient();
    const onClose = vi.fn();
    const initialProps = {
      chipId: "chip-1",
      targetId: "0",
      existing: { targetId: "0", content: "Current note", username: "tester", updatedAt: "" },
      onClose,
    };
    const { rerender } = render(
      <QueryClientProvider client={queryClient}>
        <DashboardTargetNoteModal {...initialProps} />
      </QueryClientProvider>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Unsaved draft" } });

    rerender(
      <QueryClientProvider client={queryClient}>
        <DashboardTargetNoteModal
          {...initialProps}
          existing={{
            targetId: "0",
            content: "Server refresh",
            username: "tester",
            updatedAt: "2026-07-09T00:00:00Z",
          }}
        />
      </QueryClientProvider>,
    );

    expect((screen.getByRole("textbox") as HTMLTextAreaElement).value).toBe("Unsaved draft");
  });
});

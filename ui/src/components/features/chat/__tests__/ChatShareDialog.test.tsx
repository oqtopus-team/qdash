import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ChatShareDialog, sharedChatPath } from "@/components/features/chat/ChatShareDialog";

type QueryOptions = {
  request?: unknown;
  query: { queryKey: unknown[]; enabled?: boolean };
};
type MutateOptions = { onSuccess?: () => void; onError?: (error: unknown) => void };

const mocks = vi.hoisted(() => ({
  status: {} as Record<string, unknown>,
  statusArgs: null as unknown[] | null,
  publish: vi.fn(),
  revoke: vi.fn(),
  canEdit: true,
  success: vi.fn(),
  copyText: vi.fn(),
}));

vi.mock("@/client/agent/agent", () => ({
  getGetAgentChatShareStatusQueryKey: (id: string) => [`/agent/chat/sessions/${id}/share`],
  useGetAgentChatShareStatus: (...args: unknown[]) => {
    mocks.statusArgs = args;
    return mocks.status;
  },
  usePublishAgentChatShare: () => ({ mutate: mocks.publish, isPending: false }),
  useRevokeAgentChatShare: () => ({ mutate: mocks.revoke, isPending: false }),
}));
vi.mock("@/contexts/ProjectContext", () => ({
  useProject: () => ({
    projectId: "project-1",
    currentProject: { name: "Lab A" },
    canEdit: mocks.canEdit,
  }),
}));
vi.mock("@/components/ui/Toast", () => ({
  useToast: () => ({ success: mocks.success, error: vi.fn() }),
}));
vi.mock("@/lib/utils/clipboard", () => ({ copyText: mocks.copyText }));

const SHARE = {
  share_id: "chatshare_abc",
  project_id: "project-1",
  title: "Calibrate Q5",
  message_count: 4,
  created_at: "2026-11-25T00:00:00Z",
  snapshot_at: "2026-11-25T01:00:00Z",
};

function renderDialog(props: Partial<Parameters<typeof ChatShareDialog>[0]> = {}) {
  const client = new QueryClient();
  return render(
    <QueryClientProvider client={client}>
      <ChatShareDialog
        open
        onOpenChange={vi.fn()}
        sessionId="s1"
        title="Calibrate Q5"
        running={false}
        {...props}
      />
    </QueryClientProvider>,
  );
}

beforeEach(() => {
  mocks.canEdit = true;
  mocks.status = { data: { data: { share: null } }, isLoading: false, isError: false };
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("ChatShareDialog", () => {
  it("asks the current project for the chat's sharing state", () => {
    renderDialog();
    const [sessionId, options] = mocks.statusArgs as [string, QueryOptions];
    expect(sessionId).toBe("s1");
    expect(options.request).toEqual({ headers: { "X-Project-Id": "project-1" } });
    expect(options.query.queryKey).toContain("project-1");
  });

  it("shares a snapshot of a private chat and explains that it does not update", () => {
    mocks.publish.mockImplementation((_vars: unknown, options: MutateOptions) =>
      options.onSuccess?.(),
    );
    renderDialog();
    expect(screen.getByRole("radio", { name: /Private/ })).toBeChecked();
    expect(screen.getByText(/It does not update automatically/)).toBeInTheDocument();
    expect(screen.getByText(/Tool steps, workspace files, figures/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Share snapshot" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("radio", { name: /Snapshot shared with project/ }));
    fireEvent.click(screen.getByRole("button", { name: "Share snapshot" }));
    expect(mocks.publish).toHaveBeenCalledWith({ sessionId: "s1" }, expect.any(Object));
    expect(mocks.success).toHaveBeenCalledWith("Snapshot shared with Lab A");
  });

  it("offers copy link, update and stop sharing for a shared chat", async () => {
    mocks.status = { data: { data: { share: SHARE } }, isLoading: false, isError: false };
    mocks.copyText.mockResolvedValue(undefined);
    renderDialog();
    expect(screen.getByText(/4 messages/)).toBeInTheDocument();
    expect(screen.getByText(/not shared until you update it/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Copy link" }));
    await vi.waitFor(() => expect(mocks.copyText).toHaveBeenCalled());
    expect(mocks.copyText.mock.calls[0][0]).toBe(
      `${window.location.origin}/chat/shared/chatshare_abc?project=project-1`,
    );

    fireEvent.click(screen.getByRole("button", { name: "Update snapshot" }));
    expect(mocks.publish).toHaveBeenCalledWith({ sessionId: "s1" }, expect.any(Object));

    fireEvent.click(screen.getByRole("radio", { name: /Private/ }));
    fireEvent.click(screen.getByRole("button", { name: "Stop sharing" }));
    expect(mocks.revoke).toHaveBeenCalledWith({ shareId: "chatshare_abc" }, expect.any(Object));
  });

  it("does not share while an answer is running", () => {
    mocks.status = { data: { data: { share: SHARE } }, isLoading: false, isError: false };
    renderDialog({ running: true });
    expect(screen.getByRole("button", { name: "Update snapshot" })).toBeDisabled();
  });

  it("does not let a viewer share", () => {
    mocks.canEdit = false;
    renderDialog();
    expect(screen.getByText("Viewers cannot share chats with the project")).toBeInTheDocument();
    for (const radio of screen.getAllByRole("radio")) expect(radio).toBeDisabled();
  });

  it("shows why sharing was refused", () => {
    mocks.publish.mockImplementation((_vars: unknown, options: MutateOptions) =>
      options.onError?.({
        isAxiosError: true,
        response: { status: 409, data: { detail: "This chat has answers from another project" } },
      }),
    );
    renderDialog();
    fireEvent.click(screen.getByRole("radio", { name: /Snapshot shared with project/ }));
    fireEvent.click(screen.getByRole("button", { name: "Share snapshot" }));
    expect(screen.getByRole("alert")).toHaveTextContent(/another project|Failed to share/);
  });

  it("builds a link that opens the share in its project", () => {
    expect(sharedChatPath("chatshare_a", "p 1")).toBe("/chat/shared/chatshare_a?project=p%201");
  });
});

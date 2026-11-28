import type { ReactNode } from "react";

import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { SharedChatPageContent } from "@/components/features/chat/SharedChatPageContent";

type QueryOptions = {
  request?: unknown;
  query: { queryKey: unknown[]; enabled?: boolean };
};
type MutateOptions = { onSuccess?: () => void; onError?: (error: unknown) => void };

const mocks = vi.hoisted(() => ({
  linked: { status: "ready", projectId: "project-1" } as Record<string, unknown>,
  share: {} as Record<string, unknown>,
  shareArgs: null as unknown[] | null,
  revoke: vi.fn(),
  success: vi.fn(),
  copyText: vi.fn(),
}));

vi.mock("next/link", () => ({
  default: ({
    children,
    href,
    className,
  }: {
    children: ReactNode;
    href: string;
    className?: string;
  }) => (
    <a href={href} className={className}>
      {children}
    </a>
  ),
}));
vi.mock("@/components/features/agent-session/useLinkedProject", () => ({
  useLinkedProject: () => mocks.linked,
  projectRequest: (projectId: string) => ({ headers: { "X-Project-Id": projectId } }),
}));
vi.mock("@/client/agent/agent", () => ({
  getGetAgentChatShareQueryKey: (id: string) => [`/agent/chat/shares/${id}`],
  useGetAgentChatShare: (...args: unknown[]) => {
    mocks.shareArgs = args;
    return mocks.share;
  },
  useRevokeAgentChatShare: () => ({ mutate: mocks.revoke, isPending: false }),
}));
vi.mock("@/components/features/chat/ChatMarkdown", () => ({
  ChatMarkdown: ({ children }: { children: string }) => (
    <div data-testid="markdown">{children}</div>
  ),
}));
vi.mock("@/components/features/chat/ChatPlotlyChart", () => ({
  ChatPlotlyChart: () => <div data-testid="chart" />,
}));
vi.mock("@/components/features/chat/ChatUiBlock", () => ({
  ChatUiBlock: ({ ui }: { ui: { fallback?: string } }) => <div data-testid="ui">{ui.fallback}</div>,
}));
vi.mock("@/lib/utils/clipboard", () => ({
  copyText: mocks.copyText,
}));
vi.mock("@/components/ui/Toast", () => ({
  useToast: () => ({ success: mocks.success, error: vi.fn() }),
}));

const SNAPSHOT = {
  share_id: "chatshare_abc",
  project_id: "project-1",
  title: "Calibrate Q5",
  owner_username: "alice",
  created_at: "2026-11-25T00:00:00Z",
  snapshot_at: "2026-11-25T01:00:00Z",
  is_owner: false,
  can_revoke: false,
  messages: [
    {
      role: "user",
      blocks: [{ type: "text", content: "How is Q5?" }],
      figures_attached: true,
      is_error: false,
      omitted_content: false,
    },
    {
      role: "assistant",
      blocks: [
        { type: "text", content: "Q5 is **stable**." },
        { type: "chart", chart: { data: [{ x: [1] }], layout: {} } },
        { type: "ui", content: "Summary", ui: null },
      ],
      is_error: false,
      figures_attached: false,
      omitted_content: true,
      incomplete: "stopped",
    },
    {
      role: "assistant",
      blocks: [{ type: "text", content: "Runtime unavailable" }],
      is_error: true,
      figures_attached: false,
      omitted_content: false,
    },
  ],
};

function loaded(overrides: Record<string, unknown> = {}) {
  mocks.share = {
    data: { data: { ...SNAPSHOT, ...overrides } },
    isLoading: false,
    isError: false,
    refetch: vi.fn(),
  };
}

beforeEach(() => {
  mocks.linked = { status: "ready", projectId: "project-1" };
  loaded();
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("SharedChatPageContent", () => {
  it("reads the share in the linked project", () => {
    render(<SharedChatPageContent shareId="chatshare_abc" />);
    const [shareId, options] = mocks.shareArgs as [string, QueryOptions];
    expect(shareId).toBe("chatshare_abc");
    expect(options.request).toEqual({ headers: { "X-Project-Id": "project-1" } });
    expect(options.query.queryKey).toContain("project-1");
    expect(options.query.enabled).toBe(true);
  });

  it("renders the snapshot read-only, without chat controls", () => {
    render(<SharedChatPageContent shareId="chatshare_abc" />);
    expect(screen.getByRole("heading", { name: "Calibrate Q5" })).toBeInTheDocument();
    expect(screen.getByText("by alice")).toBeInTheDocument();
    expect(screen.getByText("Shared with project")).toBeInTheDocument();
    expect(screen.getByRole("note")).toHaveTextContent(/does not update when the chat continues/);
    expect(screen.getByText("How is Q5?")).toBeInTheDocument();
    expect(screen.getByText("Figures attached")).toBeInTheDocument();
    expect(screen.getByText("Q5 is **stable**.")).toBeInTheDocument();
    expect(screen.getByTestId("chart")).toBeInTheDocument();
    expect(screen.getByTestId("ui")).toHaveTextContent("Summary");
    expect(screen.getByText("Stopped")).toBeInTheDocument();
    expect(screen.getByText("Runtime unavailable")).toBeInTheDocument();

    expect(screen.queryByRole("textbox")).not.toBeInTheDocument();
    for (const name of [
      /Edit message/,
      /Branch/,
      /Regenerate/,
      /Retry/,
      /Helpful/,
      /Stop sharing/,
    ]) {
      expect(screen.queryByRole("button", { name })).not.toBeInTheDocument();
    }
    expect(screen.getByRole("button", { name: "Copy link" })).toBeInTheDocument();
  });

  it.each([
    ["without a project", "/chat/shared/chatshare_abc"],
    ["already naming the project", "/chat/shared/chatshare_abc?project=project-1&from=forum"],
  ])("copies the share's canonical link when opened %s", async (_case, opened) => {
    const previous = window.location.href;
    window.history.replaceState(null, "", opened);
    mocks.copyText.mockResolvedValue(undefined);
    try {
      render(<SharedChatPageContent shareId="chatshare_abc" />);
      fireEvent.click(screen.getByRole("button", { name: "Copy link" }));
      await waitFor(() => expect(mocks.success).toHaveBeenCalledWith("Link copied"));
      expect(mocks.copyText).toHaveBeenCalledWith(
        `${window.location.origin}/chat/shared/chatshare_abc?project=project-1`,
      );
    } finally {
      window.history.replaceState(null, "", previous);
    }
  });

  it("lets the owner or a project owner stop sharing", () => {
    loaded({ is_owner: true, can_revoke: true });
    mocks.revoke.mockImplementation((_vars: unknown, options: MutateOptions) =>
      options.onSuccess?.(),
    );
    render(<SharedChatPageContent shareId="chatshare_abc" />);
    expect(screen.getByRole("note")).toHaveTextContent(/update it from the chat's Share dialog/);
    fireEvent.click(screen.getByRole("button", { name: "Stop sharing" }));
    fireEvent.click(screen.getAllByRole("button", { name: "Stop sharing" }).slice(-1)[0]);
    expect(mocks.revoke).toHaveBeenCalledWith({ shareId: "chatshare_abc" }, expect.any(Object));
    expect(screen.getByText("Sharing stopped")).toBeInTheDocument();
    expect(screen.queryByText("How is Q5?")).not.toBeInTheDocument();
  });

  it("reports a share that is gone or in another project", () => {
    mocks.share = {
      isLoading: false,
      isError: true,
      error: { isAxiosError: true, response: { status: 404 } },
    };
    render(<SharedChatPageContent shareId="chatshare_abc" />);
    expect(screen.getByText("This shared chat is not available")).toBeInTheDocument();
  });

  it("reports a linked project the user cannot open, without asking for the share", () => {
    mocks.linked = { status: "unavailable", projectId: "secret-project" };
    render(<SharedChatPageContent shareId="chatshare_abc" />);
    expect(screen.getByRole("alert")).toHaveTextContent(/secret-project/);
    const [, options] = mocks.shareArgs as [string, QueryOptions];
    expect(options.query.enabled).toBe(false);
  });

  it("waits for the linked project before loading", () => {
    mocks.linked = { status: "pending" };
    render(<SharedChatPageContent shareId="chatshare_abc" />);
    expect(screen.getByLabelText("Loading shared chat")).toBeInTheDocument();
    const [, options] = mocks.shareArgs as [string, QueryOptions];
    expect(options.query.enabled).toBe(false);
  });
});

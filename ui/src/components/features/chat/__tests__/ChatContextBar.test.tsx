import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { PageContextSummary } from "@/contexts/ChatDockContext";
import type { InvestigationTarget, TaskChatContext } from "@/types/agentChat";
import { ChatThread } from "../ChatThread";

const { chat, dock } = vi.hoisted(() => ({
  chat: {
    session: null as {
      id: string;
      context: TaskChatContext | null;
      investigation?: InvestigationTarget | null;
    } | null,
    send: vi.fn(),
  },
  dock: { present: true, page: null as PageContextSummary | null },
}));

vi.mock("@/client/agent/agent", () => ({
  useGetAgentPreferences: () => ({ data: undefined }),
  useListAgentSkills: () => ({ data: undefined }),
}));
vi.mock("@/contexts/ChatDockContext", () => ({
  useChatPageSummary: () => (dock.present ? dock.page : null),
}));
vi.mock("@/hooks/useAgentChat", () => ({
  useAgentChat: () => ({
    session: chat.session,
    messages: [],
    isLoadingMessages: false,
    isStreaming: false,
    liveTurn: null,
    model: { options: [], selected: { key: "default" }, select: vi.fn() },
    thinking: { choice: "auto", select: vi.fn(), modelDefault: null },
    send: chat.send,
    stop: vi.fn(),
    steers: [],
    steer: vi.fn(),
    resendSteer: vi.fn(),
    dismissSteer: vi.fn(),
    notice: null,
    dismissNotice: vi.fn(),
    continueLast: vi.fn(),
    canContinue: false,
    canEditMessage: () => false,
  }),
}));
vi.mock("@/hooks/useChatSuggestions", () => ({ useChatSuggestions: () => [] }));
vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: null, username: "" }),
}));
vi.mock("@/components/features/chat/ChatMessages", () => ({
  AssistantMessage: () => null,
  LiveAssistantMessage: () => null,
  UserMessage: () => null,
}));

const taskContext: TaskChatContext = {
  taskName: "CheckT1",
  chipId: "64Qv3",
  qid: "Q05",
  executionId: "20261119-001",
  taskId: "task-1",
};

beforeEach(() => {
  chat.session = null;
  dock.present = true;
  dock.page = null;
});
afterEach(cleanup);

const contextList = () => screen.queryByRole("list", { name: "Agent context" });

describe("ChatThread context near the composer", () => {
  it("shows nothing for a general chat on the chat page", () => {
    chat.session = { id: "s1", context: null };
    render(<ChatThread variant="page" />);
    expect(contextList()).toBeNull();
  });

  it("shows nothing where the chat renders without a dock", () => {
    dock.present = false;
    render(<ChatThread variant="compact" />);
    expect(contextList()).toBeNull();
  });

  it("shows the page a general chat sends from the sidebar, without inventing a target", () => {
    dock.page = { path: "/execution", title: "QDash", withEditorCode: false };
    render(<ChatThread variant="panel" />);
    const items = within(contextList()!).getAllByRole("listitem");
    expect(items).toHaveLength(1);
    expect(items[0]).toHaveTextContent("Page/execution");
    expect(items[0]).not.toHaveTextContent("Result");
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("says when the page sends the open editor's code", () => {
    dock.page = {
      path: "/workflow/my_flow",
      title: "Workflow editor: my_flow",
      withEditorCode: true,
    };
    render(<ChatThread variant="panel" />);
    expect(within(contextList()!).getByRole("listitem")).toHaveTextContent(
      "/workflow/my_flow · with editor code",
    );
  });

  it("says when the page sends a dashboard draft", () => {
    dock.page = {
      path: "/dashboards/new",
      title: "New dashboard",
      withEditorCode: true,
      editorKind: "dashboard",
    };
    render(<ChatThread variant="panel" />);
    expect(within(contextList()!).getByRole("listitem")).toHaveTextContent(
      "/dashboards/new · with dashboard draft",
    );
  });

  it("offers the page's own requests in an empty chat and sends one only when picked", () => {
    chat.send.mockClear();
    chat.session = { id: "s1", context: null };
    dock.page = {
      path: "/dashboards/new",
      title: "New dashboard",
      withEditorCode: true,
      editorKind: "dashboard",
      suggestions: ["Build a frequency collision map from the starter template"],
    };
    render(<ChatThread variant="panel" />);
    const pick = screen.getByRole("button", {
      name: "Build a frequency collision map from the starter template",
    });
    expect(chat.send).not.toHaveBeenCalled();
    fireEvent.click(pick);
    expect(chat.send).toHaveBeenCalledWith(
      "Build a frequency collision map from the starter template",
      [],
    );
  });

  it("separates the saved result from the current page and links the execution", () => {
    chat.session = { id: "s1", context: taskContext };
    dock.page = { path: "/chip", title: "QDash", withEditorCode: false };
    render(<ChatThread variant="compact" />);
    const [result, page] = within(contextList()!).getAllByRole("listitem");
    expect(result).toHaveTextContent("ResultCheckT1 · Q05 · 64Qv3");
    expect(result).toHaveAttribute("title", expect.stringContaining("Saved with this chat"));
    expect(result).toHaveAttribute("title", expect.stringContaining("execution 20261119-001"));
    expect(
      within(result).getByRole("link", { name: "Open execution 20261119-001" }),
    ).toHaveAttribute("href", "/execution/64Qv3/20261119-001");
    expect(page).toHaveTextContent("Page/chip");
  });

  it("shows an investigation with only the fields it knows", () => {
    chat.session = {
      id: "s2",
      context: null,
      investigation: {
        executionId: "exec-9",
        taskId: null,
        taskName: null,
        qid: null,
      },
    };
    render(<ChatThread variant="page" />);
    const item = within(contextList()!).getByRole("listitem");
    expect(item).toHaveTextContent("InvestigatingExecution exec-9");
    expect(item).not.toHaveTextContent("chip");
    // Without a chip, the id-only route forwards to the execution's page.
    expect(within(item).getByRole("link", { name: "Open execution exec-9" })).toHaveAttribute(
      "href",
      "/executions/exec-9",
    );
  });

  it("follows the session and the page as they change", () => {
    chat.session = { id: "s1", context: taskContext };
    dock.page = { path: "/chip", title: "QDash", withEditorCode: false };
    const { rerender } = render(<ChatThread variant="panel" />);
    expect(contextList()).toHaveTextContent("CheckT1");

    chat.session = {
      id: "s2",
      context: null,
      investigation: {
        executionId: "exec-9",
        taskName: "CheckRabi",
        qid: "Q01",
        chipId: "64Qv3",
      },
    };
    dock.page = { path: "/metrics", title: "QDash", withEditorCode: false };
    rerender(<ChatThread variant="panel" />);
    const items = within(contextList()!).getAllByRole("listitem");
    expect(items.map((item) => item.textContent)).toEqual([
      "InvestigatingCheckRabi · Q01 · 64Qv3",
      "Page/metrics",
    ]);
    expect(contextList()).not.toHaveTextContent("CheckT1");

    chat.session = { id: "s3", context: null };
    dock.page = null;
    rerender(<ChatThread variant="panel" />);
    expect(contextList()).toBeNull();
  });
});

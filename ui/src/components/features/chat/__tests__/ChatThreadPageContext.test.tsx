import { Profiler, useEffect, useRef, useState } from "react";
import { act, cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ChatDockProvider, useChatDock } from "@/contexts/ChatDockContext";
import type { PageContext } from "@/types/agentChat";
import { ChatThread } from "../ChatThread";

// The real dock and thread; only the route, the sessions, and the network are stubbed.
const { nav } = vi.hoisted(() => ({ nav: { pathname: "/workflow/flow_a" } }));

vi.mock("next/navigation", () => ({ usePathname: () => nav.pathname }));
vi.mock("@/contexts/AgentChatSessionContext", () => ({
  useAgentChatSessionContext: () => ({ activeSession: null }),
}));
vi.mock("@/client/agent/agent", () => ({
  useGetAgentPreferences: () => ({ data: undefined }),
  useListAgentSkills: () => ({ data: undefined }),
}));
vi.mock("@/hooks/useAgentChat", () => ({
  useAgentChat: () => ({
    session: null,
    messages: [],
    isLoadingMessages: false,
    isStreaming: false,
    liveTurn: null,
    model: { options: [], selected: { key: "default" }, select: vi.fn() },
    thinking: { choice: "auto", select: vi.fn(), modelDefault: null },
    send: vi.fn(),
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

interface EditorState {
  name: string;
  ready: boolean;
  code: string;
}

// Drives the editor's own state, so only the editor rerenders, as when it loads or is typed in.
const editor: { set: (update: Partial<EditorState>) => void } = { set: () => undefined };
let dock: ReturnType<typeof useChatDock>;

/** Registers with the dock the way the workflow editor page does: a ref read on demand. */
function FakeEditorPage() {
  const [state, setState] = useState<EditorState>({ name: "flow_a", ready: false, code: "" });
  editor.set = (update) => setState((prev) => ({ ...prev, ...update }));
  const { registerPage, refreshPage } = useChatDock();
  const pageState = useRef(state);
  useEffect(() => {
    pageState.current = state;
    refreshPage();
  });
  useEffect(
    () =>
      registerPage({
        current: (): PageContext => {
          const { name, ready, code } = pageState.current;
          return {
            path: `/workflow/${name}`,
            title: `Workflow editor: ${name}`,
            flow: ready ? { name, code, dirty: true } : undefined,
          };
        },
        applyCode: (code) => setState((prev) => ({ ...prev, code })),
      }),
    [registerPage],
  );
  return null;
}

function DockProbe() {
  dock = useChatDock();
  return null;
}

let threadRenders = 0;

function Tree({ withEditor }: { withEditor: boolean }) {
  return (
    <ChatDockProvider>
      <DockProbe />
      {withEditor && <FakeEditorPage />}
      <Profiler id="thread" onRender={() => threadRenders++}>
        <ChatThread variant="panel" />
      </Profiler>
    </ChatDockProvider>
  );
}

const pageItem = () =>
  within(screen.getByRole("list", { name: "Agent context" })).getByRole("listitem");

beforeEach(() => {
  nav.pathname = "/workflow/flow_a";
  threadRenders = 0;
});
afterEach(cleanup);

describe("ChatThread page context with the real dock", () => {
  it("tracks the editor as it loads, switches panes, and unregisters", () => {
    const { rerender } = render(<Tree withEditor />);
    // Registered but still loading: the page is named, its code is not sent.
    expect(pageItem()).toHaveTextContent("Page/workflow/flow_a");
    expect(pageItem()).not.toHaveTextContent("with editor code");
    expect(dock.currentPage()?.flow).toBeUndefined();

    // The editor finishes loading without the chat being rerendered by its parent.
    act(() => editor.set({ ready: true, code: "print(1)" }));
    expect(pageItem()).toHaveTextContent("/workflow/flow_a · with editor code");
    expect(pageItem()).toHaveAttribute("title", expect.stringContaining("Workflow editor: flow_a"));

    // Typing changes what a send carries but not what the bar shows: no chat rerender.
    const rendersBeforeTyping = threadRenders;
    act(() => editor.set({ code: "print(2)" }));
    act(() => editor.set({ code: "print(3)" }));
    expect(threadRenders).toBe(rendersBeforeTyping);
    expect(dock.currentPage()?.flow?.code).toBe("print(3)");

    // Switching to the other pane's flow updates the bar and the next send together.
    act(() => editor.set({ name: "flow_b", code: "x = 1" }));
    expect(pageItem()).toHaveTextContent("/workflow/flow_b · with editor code");
    expect(dock.currentPage()).toMatchObject({
      path: "/workflow/flow_b",
      flow: { name: "flow_b", code: "x = 1" },
    });

    // Leaving the editor unregisters it; the route alone is described.
    nav.pathname = "/metrics";
    rerender(<Tree withEditor={false} />);
    expect(pageItem()).toHaveTextContent("Page/metrics");
    expect(pageItem()).not.toHaveTextContent("with editor code");
    expect(dock.currentPage()?.flow).toBeUndefined();

    // On the chat page there is no page to describe.
    nav.pathname = "/chat";
    rerender(<Tree withEditor={false} />);
    expect(screen.queryByRole("list", { name: "Agent context" })).toBeNull();
    expect(dock.currentPage()).toBeNull();
  });

  it("shows code proposed into the editor as sent on the next turn", () => {
    render(<Tree withEditor />);
    act(() => editor.set({ ready: true, code: "old" }));
    let applied = false;
    act(() => {
      applied = dock.applyCode({
        flowName: "flow_a",
        chipId: null,
        pagePath: "/workflow/flow_a",
        code: "new",
        summary: "Update",
      });
    });
    expect(applied).toBe(true);
    expect(dock.currentPage()?.flow?.code).toBe("new");
    expect(pageItem()).toHaveTextContent("with editor code");
  });
});

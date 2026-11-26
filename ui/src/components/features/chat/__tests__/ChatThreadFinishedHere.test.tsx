import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ChatMessage as AgentMessage } from "@/types/agentChat";
import { ChatThread } from "../ChatThread";

// The chat as the hook returns it; each test moves it through a turn.
const chat: { messages: AgentMessage[]; liveTurn: object | null; sessionId: string } = {
  messages: [],
  liveTurn: null,
  sessionId: "s1",
};

vi.mock("@/client/agent/agent", () => ({
  useGetAgentPreferences: () => ({ data: undefined }),
  useListAgentSkills: () => ({ data: undefined }),
}));
vi.mock("@/hooks/useAgentChat", () => ({
  replyAfter: () => undefined,
  useAgentChat: () => ({
    session: { id: chat.sessionId, context: null },
    messages: chat.messages,
    isLoadingMessages: false,
    isStreaming: chat.liveTurn !== null,
    liveTurn: chat.liveTurn,
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
    canBranchAt: () => false,
  }),
}));
vi.mock("@/hooks/useChatSuggestions", () => ({ useChatSuggestions: () => [] }));
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ user: null, username: "" }) }));
vi.mock("@/components/features/chat/ChatMessages", () => ({
  AssistantMessage: ({
    message,
    finishedHere,
  }: {
    message: AgentMessage;
    finishedHere?: boolean;
  }) => (
    <div data-testid="answer" data-finished-here={String(Boolean(finishedHere))}>
      {message.content}
    </div>
  ),
  LiveAssistantMessage: () => <div data-testid="live" />,
  UserMessage: () => null,
}));
vi.mock("@/lib/viewTransition", () => ({ withViewTransition: (update: () => void) => update() }));

afterEach(cleanup);

const user = (content: string): AgentMessage => ({ role: "user", content });
const answer = (content: string): AgentMessage => ({ role: "assistant", content });
const marks = () =>
  Object.fromEntries(
    screen.getAllByTestId("answer").map((el) => [el.textContent, el.dataset.finishedHere]),
  );

describe("answers a turn streamed in this view", () => {
  it("marks only the answer the live turn ended in, not answers loaded with the chat", () => {
    chat.sessionId = "s1";
    chat.messages = [user("q1"), answer("loaded")];
    chat.liveTurn = null;
    const { rerender } = render(<ChatThread variant="page" />);
    expect(marks()).toEqual({ loaded: "false" });

    chat.messages = [...chat.messages, user("q2")];
    chat.liveTurn = { steps: [], startedAt: 0 };
    rerender(<ChatThread variant="page" />);
    expect(screen.getByTestId("live")).toBeInTheDocument();

    chat.messages = [...chat.messages, answer("streamed")];
    chat.liveTurn = null;
    rerender(<ChatThread variant="page" />);
    expect(marks()).toEqual({ loaded: "false", streamed: "true" });
  });

  it("marks nothing in another chat opened afterwards", () => {
    chat.sessionId = "s1";
    chat.messages = [user("q1")];
    chat.liveTurn = { steps: [], startedAt: 0 };
    const { rerender } = render(<ChatThread variant="page" />);
    chat.messages = [user("q1"), answer("streamed")];
    chat.liveTurn = null;
    rerender(<ChatThread variant="page" />);
    expect(marks()).toEqual({ streamed: "true" });

    chat.sessionId = "s2";
    chat.messages = [user("a"), answer("other"), user("b"), answer("older")];
    rerender(<ChatThread variant="page" />);
    expect(marks()).toEqual({ other: "false", older: "false" });
  });
});

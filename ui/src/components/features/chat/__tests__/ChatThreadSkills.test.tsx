import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ChatThread } from "../ChatThread";

const { send } = vi.hoisted(() => ({ send: vi.fn() }));
vi.mock("@/client/agent/agent", () => ({
  useGetAgentPreferences: () => ({ data: undefined }),
  useListAgentSkills: () => ({
    data: {
      data: {
        skills: [
          { name: "qdash-characterization", description: "Remeasure T1 and T2." },
          { name: "qcaleval", description: "Evaluate calibration plots." },
        ],
      },
    },
  }),
}));
vi.mock("@/hooks/useAgentChat", () => ({
  useAgentChat: () => ({
    session: { id: "s1", context: null },
    messages: [],
    isLoadingMessages: false,
    isStreaming: false,
    liveTurn: null,
    model: { options: [], selected: { key: "default" }, select: vi.fn() },
    thinking: { choice: "auto", select: vi.fn(), modelDefault: null },
    send,
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
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ user: null, username: "" }) }));
vi.mock("@/components/features/chat/ChatMessages", () => ({
  AssistantMessage: () => null,
  LiveAssistantMessage: () => null,
  UserMessage: () => null,
}));
vi.mock("@/lib/viewTransition", () => ({ withViewTransition: (update: () => void) => update() }));

afterEach(cleanup);
beforeEach(() => {
  send.mockReset();
  send.mockReturnValue(true);
});

describe("ChatThread skill commands", () => {
  it.each(["page", "panel", "compact"] as const)(
    "sends a picked skill with its arguments as /skill:<name> on the %s surface",
    (variant) => {
      render(<ChatThread variant={variant} />);
      const box = screen.getByRole("combobox", { name: "Message" });
      act(() => box.focus());
      fireEvent.change(box, { target: { value: "/char" } });
      fireEvent.keyDown(box, { key: "Enter" });
      expect(send).not.toHaveBeenCalled();
      expect(box).toHaveValue("/skill:qdash-characterization ");

      fireEvent.change(box, { target: { value: "/skill:qdash-characterization T1 of Q0" } });
      fireEvent.keyDown(box, { key: "Enter" });
      expect(send).toHaveBeenCalledWith("/skill:qdash-characterization T1 of Q0", []);
      expect(box).toHaveValue("");
    },
  );
});

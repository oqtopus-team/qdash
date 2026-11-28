import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { stageAttachment, type StagedAttachment } from "@/lib/chatAttachments";
import { ChatThread } from "../ChatThread";

const { send, steer, chat } = vi.hoisted(() => ({
  send: vi.fn(),
  steer: vi.fn(),
  chat: { isStreaming: false, steers: [] as unknown[], notice: null as string | null },
}));
vi.mock("@/client/agent/agent", () => ({
  useGetAgentPreferences: () => ({ data: undefined }),
  useListAgentSkills: () => ({ data: undefined }),
}));
vi.mock("@/hooks/useAgentChat", () => ({
  useAgentChat: () => ({
    session: { id: "s1", context: null },
    messages: [],
    isLoadingMessages: false,
    isStreaming: chat.isStreaming,
    liveTurn: null,
    model: { options: [], selected: { key: "default" }, select: vi.fn() },
    thinking: { choice: "auto", select: vi.fn(), modelDefault: null },
    send,
    stop: vi.fn(),
    steers: chat.steers,
    steer,
    resendSteer: vi.fn(),
    dismissSteer: vi.fn(),
    notice: chat.notice,
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
vi.mock("@/lib/chatAttachments", async (original) => ({
  ...(await original<typeof import("@/lib/chatAttachments")>()),
  stageAttachment: vi.fn(),
}));

afterEach(cleanup);

const image: StagedAttachment = {
  id: "plot",
  name: "plot.png",
  data: "iVBORw0KGgo=",
  mimeType: "image/png",
  previewUrl: "data:image/png;base64,iVBORw0KGgo=",
};
beforeEach(() => {
  send.mockReset();
  steer.mockReset();
  chat.isStreaming = false;
  chat.steers = [];
  chat.notice = null;
  vi.mocked(stageAttachment).mockReset();
});

describe("ChatThread attachment submission", () => {
  it("keeps the draft until staging finishes and the turn is accepted", async () => {
    let finish!: (image: StagedAttachment) => void;
    vi.mocked(stageAttachment).mockReturnValue(
      new Promise((resolve) => {
        finish = resolve;
      }),
    );
    const { container } = render(<ChatThread variant="page" />);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "Evaluate" } });
    fireEvent.change(container.querySelector('input[type="file"]')!, {
      target: { files: [new File(["x"], "plot.png", { type: "image/png" })] },
    });
    fireEvent.submit(screen.getByRole("textbox").closest("form")!);
    expect(send).not.toHaveBeenCalled();
    await act(async () => finish(image));
    await waitFor(() => expect(screen.getByAltText("plot.png")).toBeInTheDocument());

    send.mockReturnValue(false);
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));
    expect(screen.getByRole("textbox")).toHaveValue("Evaluate");
    expect(screen.getByAltText("plot.png")).toBeInTheDocument();

    send.mockReturnValue(true);
    fireEvent.click(screen.getByRole("button", { name: "Send message" }));
    expect(send).toHaveBeenLastCalledWith("Evaluate", [
      { data: image.data, mimeType: image.mimeType },
    ]);
    expect(screen.getByRole("textbox")).toHaveValue("");
    expect(screen.queryByAltText("plot.png")).not.toBeInTheDocument();
  });

  it("sends while an answer streams as a steer, not as a new turn", () => {
    chat.isStreaming = true;
    steer.mockReturnValue(true);
    render(<ChatThread variant="panel" />);
    const box = screen.getByRole("textbox");
    expect(box).toHaveAttribute("placeholder", "Add a note; it is read after the current step");
    // Nothing typed: only Stop.
    expect(screen.queryByRole("button", { name: "Send to the answer in progress" })).toBeNull();
    expect(screen.getByRole("button", { name: "Stop generating" })).toBeInTheDocument();

    fireEvent.change(box, { target: { value: "Use Q5 instead" } });
    fireEvent.keyDown(box, { key: "Enter" });
    expect(steer).toHaveBeenCalledWith("Use Q5 instead");
    expect(send).not.toHaveBeenCalled();
    expect(box).toHaveValue("");
  });

  it("keeps the text when the steer could not be sent", () => {
    chat.isStreaming = true;
    steer.mockReturnValue(false);
    render(<ChatThread variant="panel" />);
    const box = screen.getByRole("textbox");
    fireEvent.change(box, { target: { value: "Use Q5" } });
    fireEvent.click(screen.getByRole("button", { name: "Send to the answer in progress" }));
    expect(steer).toHaveBeenCalledWith("Use Q5");
    expect(box).toHaveValue("Use Q5");
  });
});

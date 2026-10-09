import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { stageAttachment, type StagedAttachment } from "@/lib/chatAttachments";
import { ChatThread } from "../ChatThread";

const { send } = vi.hoisted(() => ({ send: vi.fn() }));
vi.mock("@/hooks/useCopilotChat", () => ({
  useCopilotChat: () => ({
    session: { id: "s1", context: null },
    messages: [],
    isLoadingMessages: false,
    isStreaming: false,
    liveTurn: null,
    model: { options: [], selected: { key: "default" }, select: vi.fn() },
    send,
    stop: vi.fn(),
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
});

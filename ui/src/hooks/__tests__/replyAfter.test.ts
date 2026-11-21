import { describe, expect, it } from "vitest";
import type { ChatMessage } from "@/types/copilotChat";
import { replyAfter } from "../useCopilotChat";

const approvalCard: ChatMessage = {
  role: "assistant",
  content: JSON.stringify({
    blocks: [
      {
        type: "approval",
        content: "",
        approval: { id: "call-1", tool: "qdash_save_flow", label: "Save Flow", args: {} },
      },
    ],
    assessment: null,
  }),
};

// What the runtime streams for the approved call before it places the decision.
const approvedRunTrace: ChatMessage = {
  role: "assistant",
  content: JSON.stringify({
    blocks: [],
    assessment: null,
    trace: { steps: [{ kind: "tool", name: "qdash_save_flow" }] },
  }),
};

const decision: ChatMessage = { role: "user", content: "Approved: Save Flow" };

describe("replyAfter", () => {
  it("reads the user message right after an answer", () => {
    expect(replyAfter([approvalCard, decision], 0)).toBe("Approved: Save Flow");
  });

  it("passes over the approved call's trace placed before the decision", () => {
    const messages = [approvalCard, approvedRunTrace, decision];
    expect(replyAfter(messages, 0)).toBe("Approved: Save Flow");
  });

  it("finds no reply when another answer comes in between", () => {
    const answer: ChatMessage = {
      role: "assistant",
      content: JSON.stringify({ blocks: [{ type: "text", content: "Done" }] }),
    };
    expect(replyAfter([approvalCard, answer, decision], 0)).toBeUndefined();
    expect(replyAfter([approvalCard, { role: "assistant", content: "plain" }, decision], 0)).toBe(
      undefined,
    );
  });

  it("finds no reply at the end of the conversation", () => {
    expect(replyAfter([approvalCard], 0)).toBeUndefined();
    expect(replyAfter([approvalCard, approvedRunTrace], 0)).toBeUndefined();
  });
});

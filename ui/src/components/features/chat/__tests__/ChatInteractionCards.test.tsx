import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ApprovalCard, AskCard, type InteractionState } from "../ChatInteractionCards";

afterEach(cleanup);

function state(overrides: Partial<InteractionState> = {}): InteractionState {
  return {
    active: true,
    onAnswer: vi.fn(),
    onDecide: vi.fn(),
    onOther: vi.fn(),
    ...overrides,
  };
}

const ASK = {
  question: "Which qubit should I recalibrate?",
  options: [{ label: "Q32", description: "Rabi angle dropped" }, { label: "Q33" }],
};

const APPROVAL = {
  id: "call-1",
  tool: "qdash_execute_agent_action",
  label: "QDash Execute Agent Action",
  args: { sessionId: "s1", sourceExecutionId: "20261005-005" },
};

describe("AskCard", () => {
  it("sends the chosen option as the reply", () => {
    const s = state();
    render(<AskCard ask={ASK} state={s} />);

    fireEvent.click(screen.getByRole("button", { name: /Q32/ }));
    expect(s.onAnswer).toHaveBeenCalledWith("Q32");

    fireEvent.click(screen.getByRole("button", { name: /Something else/ }));
    expect(s.onOther).toHaveBeenCalled();
  });

  it("locks once answered and marks the pick", () => {
    render(<AskCard ask={ASK} state={state({ active: false, answer: "Q33" })} />);

    const buttons = screen.getAllByRole("button");
    expect(buttons.every((b) => (b as HTMLButtonElement).disabled)).toBe(true);
    expect(screen.getByRole("button", { name: /Q33/ }).className).toContain("chat-option-chosen");
    expect(screen.queryByRole("button", { name: /Something else/ })).toBeNull();
  });
});

describe("ApprovalCard", () => {
  it("shows the exact arguments and reports the decision", () => {
    const s = state();
    render(<ApprovalCard approval={APPROVAL} state={s} />);

    expect(screen.getByText("sourceExecutionId")).toBeTruthy();
    expect(screen.getByText("20261005-005")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: /Approve/ }));
    expect(s.onDecide).toHaveBeenCalledWith("call-1", true, "Approved: QDash Execute Agent Action");
    fireEvent.click(screen.getByRole("button", { name: "Decline" }));
    expect(s.onDecide).toHaveBeenCalledWith(
      "call-1",
      false,
      "Declined: QDash Execute Agent Action",
    );
  });

  it("shows the recorded decision instead of buttons", () => {
    render(
      <ApprovalCard
        approval={APPROVAL}
        state={state({ active: false, answer: "Approved: QDash Execute Agent Action" })}
      />,
    );
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByText("Approved")).toBeTruthy();
  });
});

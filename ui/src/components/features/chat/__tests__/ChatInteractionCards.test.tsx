import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import {
  ApprovalCard,
  AskCard,
  EditProposalCard,
  type InteractionState,
} from "../ChatInteractionCards";

vi.mock("@/components/ui/PierreDiffViewer", () => ({
  PierreDiffViewer: ({ oldContent, newContent }: { oldContent: string; newContent: string }) => (
    <div data-testid="diff">{`${oldContent}=>${newContent}`}</div>
  ),
}));

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

  it("shows a flow about to be saved as code, not as a JSON string", () => {
    const code = "from prefect import flow\n\n@flow\ndef t1_sweep():\n    pass\n";
    render(
      <ApprovalCard
        approval={{
          id: "call-2",
          tool: "qdash_save_flow",
          label: "QDash Save Flow",
          args: {
            name: "t1_sweep",
            chipId: "64Qv3",
            code,
            description: "T1 across the chip",
            tags: ["check"],
          },
        }}
        state={state()}
      />,
    );
    const preview = screen.getByTestId("flow-save-preview");
    expect(preview.textContent).toContain("t1_sweep");
    expect(preview.textContent).toContain("64Qv3");
    expect(preview.textContent).toContain("T1 across the chip");
    expect(preview.textContent).toContain("def t1_sweep():");
    expect(screen.queryByText(/"code"/)).toBeNull();
    expect(screen.queryByText("code", { selector: "dt" })).toBeNull();
  });
});

describe("EditProposalCard", () => {
  const edit = {
    summary: "Add a T2 step",
    code: "new code\n",
    flowName: "t1_check",
    chipId: "chip1",
    pagePath: "/workflow/t1_check",
  };

  it("shows the diff against the open editor and applies the code there", () => {
    const applyCode = vi.fn(() => true);
    render(
      <EditProposalCard
        edit={edit}
        state={state({ applyCode, currentCode: () => "old code\n" })}
      />,
    );
    expect(screen.getByText("Add a T2 step")).toBeTruthy();
    expect(screen.getByTestId("diff").textContent).toBe("old code\n=>new code\n");
    fireEvent.click(screen.getByRole("button", { name: "Apply to editor" }));
    expect(applyCode).toHaveBeenCalledWith(edit);
    expect(screen.getByText(/Applied to the editor/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Apply to editor" })).toBeNull();
  });

  it("shows the code alone and says where to apply it when no editor is open", () => {
    render(<EditProposalCard edit={edit} state={state()} />);
    expect(screen.queryByTestId("diff")).toBeNull();
    expect(screen.getByText(/Open this flow in the Workflow editor/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Apply to editor" })).toBeNull();
  });

  it("can be discarded", () => {
    render(
      <EditProposalCard
        edit={edit}
        state={state({ applyCode: () => true, currentCode: () => "x" })}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Discard" }));
    expect(screen.getByText("Discarded")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Discard" })).toBeNull();
  });

  it("does not offer Apply when the open editor is a different target", () => {
    const applyCode = vi.fn();
    render(<EditProposalCard edit={edit} state={state({ applyCode, currentCode: () => null })} />);
    expect(screen.queryByRole("button", { name: "Apply to editor" })).toBeNull();
    expect(screen.queryByTestId("diff")).toBeNull();
    expect(applyCode).not.toHaveBeenCalled();
  });

  it("shows the new diff instead of applying when the editor changed since the diff was made", () => {
    const applyCode = vi.fn(() => true);
    let live = "old code\n";
    render(<EditProposalCard edit={edit} state={state({ applyCode, currentCode: () => live })} />);
    expect(screen.getByTestId("diff").textContent).toBe("old code\n=>new code\n");
    live = "old code\n# typed meanwhile\n";
    fireEvent.click(screen.getByRole("button", { name: "Apply to editor" }));
    expect(applyCode).not.toHaveBeenCalled();
    expect(screen.getByRole("status").textContent).toMatch(/editor changed since this diff/);
    expect(screen.getByTestId("diff").textContent).toBe(
      "old code\n# typed meanwhile\n=>new code\n",
    );
    // The second click applies against the diff now shown.
    fireEvent.click(screen.getByRole("button", { name: "Apply to editor" }));
    expect(applyCode).toHaveBeenCalledWith(edit);
    expect(screen.getByText(/Applied to the editor/)).toBeTruthy();
  });

  it("does not report success if the target changed before the click", () => {
    render(
      <EditProposalCard
        edit={edit}
        state={state({ applyCode: () => false, currentCode: () => "old" })}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Apply to editor" }));
    expect(screen.queryByText(/Applied to the editor/)).toBeNull();
  });
});

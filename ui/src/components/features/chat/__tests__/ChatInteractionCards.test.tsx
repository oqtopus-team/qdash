import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
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

  it("names the action and tool before the arguments and asks before running", () => {
    render(<ApprovalCard approval={APPROVAL} state={state()} />);

    const card = screen.getByRole("group", { name: "Approve QDash Execute Agent Action" });
    expect(card.getAttribute("data-decision")).toBe("pending");
    const text = card.textContent ?? "";
    expect(text.indexOf("QDash Execute Agent Action")).toBeLessThan(
      text.indexOf("qdash_execute_agent_action"),
    );
    expect(text.indexOf("qdash_execute_agent_action")).toBeLessThan(text.indexOf("sessionId"));
    expect(screen.getByText("Runs only if you approve")).toBeTruthy();
    // The card is neutral: no decorative status icon competes with the title.
    expect(card.querySelector(".text-warning")).toBeNull();
  });

  it("keeps nested and long argument values inspectable", () => {
    const longValue = "x".repeat(300);
    render(
      <ApprovalCard
        approval={{
          ...APPROVAL,
          args: { qubits: ["Q00", "Q01"], options: { retries: 2 }, note: longValue },
        }}
        state={state()}
      />,
    );
    expect(screen.getAllByRole("term").map((dt) => dt.textContent)).toEqual([
      "qubits",
      "options",
      "note",
    ]);
    expect(screen.getByText(/"Q01"/).textContent).toContain('"Q00"');
    expect(screen.getByText(/"retries": 2/)).toBeTruthy();
    expect(screen.getByText(longValue)).toBeTruthy();
  });

  it("says so when the call has no arguments", () => {
    render(<ApprovalCard approval={{ ...APPROVAL, args: {} }} state={state()} />);
    expect(screen.getByText("No arguments")).toBeTruthy();
  });

  it("shows the recorded decision instead of buttons", () => {
    render(
      <ApprovalCard
        approval={APPROVAL}
        state={state({ active: false, answer: "Approved: QDash Execute Agent Action" })}
      />,
    );
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByRole("status").textContent).toBe("Approved");
    expect(screen.getByRole("group").getAttribute("data-decision")).toBe("approved");
  });

  it("shows a decline as recorded", () => {
    render(
      <ApprovalCard
        approval={APPROVAL}
        state={state({ active: false, answer: "Declined: QDash Execute Agent Action" })}
      />,
    );
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByRole("status").textContent).toBe("Declined");
    expect(screen.getByRole("group").getAttribute("data-decision")).toBe("declined");
  });

  it("offers no decision once the card is no longer the latest answer", () => {
    render(<ApprovalCard approval={APPROVAL} state={state({ active: false })} />);
    expect(screen.queryByRole("button")).toBeNull();
    expect(screen.getByText("No decision was made")).toBeTruthy();
    expect(screen.queryByText("Runs only if you approve")).toBeNull();
    expect(screen.getByText("20261005-005")).toBeTruthy();
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
    expect(preview.textContent).toContain("replaces a flow of the same name");
    expect(preview.textContent).toContain("does not run it");
  });

  it("keeps flow-save arguments that have no preview in the argument list", () => {
    render(
      <ApprovalCard
        approval={{
          id: "call-3",
          tool: "qdash_save_flow",
          label: "QDash Save Flow",
          args: { name: "t1_sweep", code: "pass\n", overwrite: true },
        }}
        state={state()}
      />,
    );
    expect(screen.getByText("overwrite", { selector: "dt" })).toBeTruthy();
    expect(screen.getByText("true")).toBeTruthy();
    expect(screen.getByTestId("flow-save-preview").textContent).toContain("on the session's chip");
  });
});

describe("ApprovalCard for agent sessions", () => {
  const policy = {
    qids: ["Q00"],
    allowed_tasks: ["CheckChevron", "CheckRabi"],
    allowed_overrides: { qubit_frequency: { minimum: 7.0, maximum: 8.0 } },
    autonomy: "auto",
    max_actions: 4,
  };

  it("states granted parameter updates before the exact policy", () => {
    render(
      <ApprovalCard
        approval={{
          id: "call-s",
          tool: "qdash_create_agent_session",
          label: "QDash Create Agent Session",
          args: {
            chipId: "64Q",
            expiresInSeconds: 3600,
            policy: {
              ...policy,
              parameter_updates: {
                parameters: ["qubit_frequency"],
                tasks: ["CheckChevron"],
                apply_backend: false,
              },
            },
          },
        }}
        state={state()}
      />,
    );

    const preview = screen.getByTestId("agent-session-policy-preview");
    expect(preview.textContent).toContain("granted");
    expect(preview.textContent).toContain("qubit_frequency [7, 8]");
    expect(preview.textContent).toContain("no backend apply");
    expect(preview.textContent).toContain("up to 4 actions");
    expect(preview.textContent).toContain("60 min");
    const criteria = within(screen.getByTestId("agent-session-update-criteria"));
    expect(
      criteria.getByText("qubit_frequency", { selector: "dt" }).nextElementSibling?.textContent,
    ).toBe("[7, 8]");
    // The exact policy stays reviewable as an argument.
    expect(screen.getByText("policy")).toBeTruthy();
  });

  it("says that commits still ask when no updates are granted", () => {
    render(
      <ApprovalCard
        approval={{
          id: "call-t",
          tool: "qdash_create_agent_session",
          label: "QDash Create Agent Session",
          args: { chipId: "64Q", policy },
        }}
        state={state()}
      />,
    );

    const preview = screen.getByTestId("agent-session-policy-preview");
    expect(preview.textContent).toContain("not granted: each commit asks you");
    expect(preview.textContent).toContain("QDash default (6 h)");
    expect(
      within(preview).getByText("Evaluation", { selector: "dt" }).nextElementSibling?.textContent,
    ).toBe("off: qcal_evaluate is not called");
  });

  it("shows each quality gate with the only task whose results it checks", () => {
    render(
      <ApprovalCard
        approval={{
          id: "call-g",
          tool: "qdash_create_agent_session",
          label: "QDash Create Agent Session",
          args: {
            chipId: "64Q",
            policy: {
              ...policy,
              allowed_overrides: {},
              task_quality_gates: { CheckRabi: { r2: { minimum: 0.9 } } },
              parameter_updates: { parameters: ["qubit_frequency"], tasks: ["CheckChevron"] },
            },
          },
        }}
        state={state()}
      />,
    );

    const preview = screen.getByTestId("agent-session-policy-preview");
    const gates = within(preview).getByText("Quality gates", { selector: "dt" });
    expect(gates.nextElementSibling?.textContent).toBe("r2 [0.9, inf] only on CheckRabi results");
    expect(preview.textContent).not.toContain("Session-wide gates");
    // A granted parameter without bounds says the task's own checks decide.
    const criteria = within(screen.getByTestId("agent-session-update-criteria"));
    expect(
      criteria.getByText("qubit_frequency", { selector: "dt" }).nextElementSibling?.textContent,
    ).toBe("no numeric bounds: its task's own checks decide");
  });
});

describe("ApprovalCard for metric scripts", () => {
  it("shows a metric script about to be saved as code", () => {
    const source =
      "from qdash_metrics import metric\n\n@metric(title='T1', unit='us')\ndef t1(q, ctx):\n    return None\n";
    render(
      <ApprovalCard
        approval={{
          id: "call-3",
          tool: "qdash_save_metric_script",
          label: "QDash Save Metric Script",
          args: {
            scriptId: "ms_1",
            name: "coherence",
            visibility: "project",
            description: "T1 per qubit",
            source,
            expectedRevision: 3,
          },
        }}
        state={state()}
      />,
    );
    const preview = screen.getByTestId("metric-script-save-preview");
    expect(preview.textContent).toContain("Update metric script coherence");
    expect(preview.textContent).toContain("shared with project");
    expect(preview.textContent).toContain("T1 per qubit");
    expect(preview.textContent).toContain("def t1(q, ctx):");
    expect(screen.queryByText("source", { selector: "dt" })).toBeNull();
    // Arguments the preview does not show stay in the list.
    expect(screen.getByText("expectedRevision", { selector: "dt" })).toBeTruthy();
  });
});

describe("EditProposalCard for metric scripts", () => {
  const edit = {
    summary: "Count observations",
    code: "new script\n",
    target: "metric_script" as const,
    flowName: "zx90",
    chipId: null,
    scriptId: "ms_1",
    scriptName: "zx90_median",
    pagePath: "/dashboards/scripts/ms_1",
  };

  it("names the script and its file", () => {
    render(
      <EditProposalCard
        edit={edit}
        state={state({ applyCode: () => true, currentCode: () => "old script\n" })}
      />,
    );
    expect(screen.getByRole("group", { name: "Proposed change to zx90_median" })).toBeTruthy();
    expect(screen.getByText(/Proposed change to metric script/)).toBeTruthy();
    expect(screen.getByTestId("diff").textContent).toBe("old script\n=>new script\n");
  });

  it("says where to apply it when the script editor is not open", () => {
    render(<EditProposalCard edit={edit} state={state()} />);
    expect(
      screen.getByText("Open this metric script in its editor to apply the change there."),
    ).toBeTruthy();
    expect(screen.queryByText(/Workflow editor/)).toBeNull();
  });
});

describe("EditProposalCard for dashboards", () => {
  const edit = {
    summary: "Add a ZX90 map",
    code: '{\n  "panels": [1]\n}\n',
    target: "dashboard" as const,
    flowName: "Collision review",
    chipId: null,
    dashboardId: "dash-1",
    pagePath: "/dashboards/dash-1",
  };

  it("diffs the dashboard draft and applies it to the draft, not a save", () => {
    const applyCode = vi.fn(() => true);
    render(
      <EditProposalCard
        edit={edit}
        state={state({ applyCode, currentCode: () => '{\n  "panels": []\n}\n' })}
      />,
    );
    expect(screen.getByRole("group", { name: "Proposed change to Collision review" })).toBeTruthy();
    expect(screen.getByText(/Proposed change to dashboard/)).toBeTruthy();
    expect(screen.getByTestId("diff").textContent).toBe(
      '{\n  "panels": []\n}\n=>{\n  "panels": [1]\n}\n',
    );
    fireEvent.click(screen.getByRole("button", { name: "Apply to draft" }));
    expect(applyCode).toHaveBeenCalledWith(edit);
    expect(
      screen.getByText("Applied to the dashboard draft. Review the panels, then Save."),
    ).toBeTruthy();
  });

  it("re-diffs instead of applying when the draft changed since the proposal", () => {
    const applyCode = vi.fn(() => true);
    let live = '{\n  "panels": []\n}\n';
    render(<EditProposalCard edit={edit} state={state({ applyCode, currentCode: () => live })} />);
    live = '{\n  "panels": [0]\n}\n';
    fireEvent.click(screen.getByRole("button", { name: "Apply to draft" }));
    expect(applyCode).not.toHaveBeenCalled();
    expect(screen.getByRole("status").textContent).toMatch(/dashboard draft changed/);
  });

  it("is not marked applied when the page refuses the draft", () => {
    render(
      <EditProposalCard
        edit={edit}
        state={state({ applyCode: () => false, currentCode: () => "{}" })}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Apply to draft" }));
    expect(screen.queryByText(/Applied to the dashboard draft/)).toBeNull();
    expect(screen.getByRole("button", { name: "Apply to draft" })).toBeTruthy();
  });

  it("says where to apply it when the dashboard is not open", () => {
    render(<EditProposalCard edit={edit} state={state()} />);
    expect(screen.getByText(/Open this dashboard, as a member who can edit it/)).toBeTruthy();
    expect(screen.queryByRole("button", { name: "Apply to draft" })).toBeNull();
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

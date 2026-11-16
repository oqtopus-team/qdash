import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TooltipProvider } from "@/components/ui/Tooltip";
import { AssistantMessage } from "../ChatMessages";

vi.mock("@/components/features/chat/ChatPlotlyChart", () => ({ ChatPlotlyChart: () => null }));

afterEach(cleanup);

const ANSWER = JSON.stringify({
  blocks: [{ type: "text", content: "T1 is 45 us.", chart: null }],
  assessment: null,
});

function renderAnswer(props: { canBranch?: boolean; branching?: boolean; isLast?: boolean }) {
  const onBranch = vi.fn();
  render(
    <TooltipProvider>
      <AssistantMessage
        message={{ role: "assistant", content: ANSWER, entryId: "17" }}
        isLast={props.isLast ?? false}
        canRetry
        onRetry={vi.fn()}
        onAnswer={vi.fn()}
        onDecide={vi.fn()}
        onOther={vi.fn()}
        onRate={vi.fn()}
        canBranch={props.canBranch}
        branching={props.branching}
        onBranch={onBranch}
      />
    </TooltipProvider>,
  );
  return { onBranch };
}

describe("branching from an answer", () => {
  it("offers Branch from here with what it shares, before the user clicks", () => {
    const { onBranch } = renderAnswer({ canBranch: true });
    const button = screen.getByRole("button", { name: "Branch from here" });
    // The disclosure is part of the control, not a later prompt.
    expect(button).toHaveAccessibleDescription(/workspace files as they are now/);
    expect(button).toHaveAccessibleDescription(/only one of the two can answer at a time/);
    fireEvent.click(button);
    expect(onBranch).toHaveBeenCalledTimes(1);
  });

  it("shows progress in place while the branch is created, and no action when it cannot branch", () => {
    renderAnswer({ branching: true });
    const busy = screen.getByRole("button", { name: "Creating branch" });
    expect(busy).toBeDisabled();
    cleanup();
    renderAnswer({ canBranch: false, isLast: true });
    expect(screen.queryByRole("button", { name: "Branch from here" })).toBeNull();
    expect(screen.getByRole("button", { name: "Regenerate" })).toBeInTheDocument();
  });
});

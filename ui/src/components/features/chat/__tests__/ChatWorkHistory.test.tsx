import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TooltipProvider } from "@/components/ui/Tooltip";
import type { ChatTrace } from "@/types/agentChat";

import { AssistantMessage } from "../ChatMessages";
import { ChatTraceSummary } from "../ChatTrace";

vi.mock("@/components/features/chat/ChatPlotlyChart", () => ({ ChatPlotlyChart: () => null }));
vi.mock("@/client/execution/execution", () => ({ useGetExecution: () => ({ data: undefined }) }));

// Whether the thread follows its bottom; the tests move the user away and back.
let following = true;
vi.mock("@/contexts/ChatFollowContext", () => ({
  useChatFollowing: () => following,
}));

beforeEach(() => {
  following = true;
});
afterEach(cleanup);

const UPDATE = "Checking the latest T1 results.";

const trace: ChatTrace = {
  durationMs: 12_000,
  steps: [
    { kind: "text", text: UPDATE },
    {
      kind: "tool",
      id: "a",
      tool: "qdash_get_figure",
      label: "Get figure",
      status: "done",
      startedAt: 0,
      endedAt: 1000,
    },
  ],
};

const folded = () => screen.queryByTestId("work-history-summary")?.getAttribute("aria-expanded");
const updateHidden = () => screen.getByText(UPDATE).closest("[hidden]") !== null;

describe("work history as an answer ends", () => {
  it("folds at once when the thread follows the bottom", () => {
    render(<ChatTraceSummary trace={trace} foldable finishedHere />);
    expect(folded()).toBe("false");
    expect(updateHidden()).toBe(true);
  });

  it("keeps the work as it streamed while the user reads above, and folds once they follow again", () => {
    following = false;
    const { rerender } = render(<ChatTraceSummary trace={trace} foldable finishedHere />);
    expect(screen.queryByTestId("work-history-summary")).toBeNull();
    expect(updateHidden()).toBe(false);

    // Still reading: a re-render changes nothing.
    rerender(<ChatTraceSummary trace={trace} foldable finishedHere />);
    expect(updateHidden()).toBe(false);

    following = true;
    rerender(<ChatTraceSummary trace={trace} foldable finishedHere />);
    expect(folded()).toBe("false");
    expect(updateHidden()).toBe(true);
  });

  it("folds an answer loaded with the chat, wherever the user is", () => {
    following = false;
    render(<ChatTraceSummary trace={trace} foldable />);
    expect(folded()).toBe("false");
    expect(updateHidden()).toBe(true);
  });
});

describe("work history of an answer that did not end", () => {
  function renderAnswer(extra: Record<string, unknown>) {
    const content = JSON.stringify({
      blocks: [{ type: "text", content: "Q3 looks low so far" }],
      assessment: null,
      trace,
      ...extra,
    });
    render(
      <TooltipProvider>
        <AssistantMessage
          message={{ role: "assistant", content }}
          isLast
          canRetry
          onRetry={vi.fn()}
          onAnswer={vi.fn()}
          onDecide={vi.fn()}
          onOther={vi.fn()}
          onRate={vi.fn()}
        />
      </TooltipProvider>,
    );
  }

  it("folds the work behind a complete answer", () => {
    renderAnswer({});
    expect(folded()).toBe("false");
  });

  it.each([{ stopped: true }, { interrupted: true }, { in_progress: true }])(
    "keeps the work shown for a partial answer (%o)",
    (state) => {
      renderAnswer(state);
      expect(screen.queryByTestId("work-history-summary")).toBeNull();
      expect(updateHidden()).toBe(false);
      expect(screen.getByText("Q3 looks low so far")).toBeInTheDocument();
    },
  );
});

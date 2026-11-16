import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TooltipProvider } from "@/components/ui/Tooltip";
import { AssistantMessage } from "../ChatMessages";

vi.mock("@/components/features/chat/ChatPlotlyChart", () => ({ ChatPlotlyChart: () => null }));

afterEach(cleanup);

function renderAnswer(content: string, canContinue: boolean) {
  const onContinue = vi.fn();
  const onRetry = vi.fn();
  render(
    <TooltipProvider>
      <AssistantMessage
        message={{ role: "assistant", content }}
        isLast
        canRetry
        onRetry={onRetry}
        onAnswer={vi.fn()}
        onDecide={vi.fn()}
        onOther={vi.fn()}
        onRate={vi.fn()}
        canContinue={canContinue}
        onContinue={onContinue}
      />
    </TooltipProvider>,
  );
  return { onContinue, onRetry };
}

describe("continuing an answer", () => {
  it("offers Continue next to Retry on a failed answer", () => {
    const { onContinue, onRetry } = renderAnswer("Error: model_error", true);
    fireEvent.click(screen.getByRole("button", { name: /Continue/ }));
    expect(onContinue).toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: /Retry/ }));
    expect(onRetry).toHaveBeenCalled();
  });

  it("offers Continue on a stopped answer, and not when it cannot continue", () => {
    const stopped = JSON.stringify({ blocks: [], assessment: null, stopped: true });
    const { onContinue } = renderAnswer(stopped, true);
    fireEvent.click(screen.getByRole("button", { name: "Continue" }));
    expect(onContinue).toHaveBeenCalled();
    cleanup();
    renderAnswer(stopped, false);
    expect(screen.queryByRole("button", { name: "Continue" })).toBeNull();
    expect(screen.getByRole("button", { name: "Regenerate" })).toBeInTheDocument();
  });
});

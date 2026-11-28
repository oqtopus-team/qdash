import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { TooltipProvider } from "@/components/ui/Tooltip";
import { AssistantMessage } from "../ChatMessages";

vi.mock("@/components/features/chat/ChatPlotlyChart", () => ({ ChatPlotlyChart: () => null }));

afterEach(cleanup);

function renderError(content: string, isLast = true) {
  render(
    <TooltipProvider>
      <AssistantMessage
        message={{ role: "assistant", content }}
        isLast={isLast}
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

describe("reporting a chat error", () => {
  it("drafts a reviewable report for a server fault and keeps the failure shown", () => {
    renderError("Error: HTTP 500: Traceback at http://10.0.0.5/v1 token=abc");
    // The failure stays visible as it was; nothing claims the turn ran.
    expect(screen.getByText(/HTTP 500: Traceback/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Retry/ })).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Report this error" }));
    const draft = screen.getByRole("textbox", { name: "Bug report draft" }) as HTMLTextAreaElement;
    expect(draft.readOnly).toBe(true);
    expect(draft.value).toContain("HTTP status: 500");
    expect(draft.value).not.toContain("10.0.0.5");
    expect(draft.value).not.toContain("token=abc");
    const link = screen.getByRole("link", { name: /Open the GitHub bug form/ });
    expect(link.getAttribute("href")).toBe(
      "https://github.com/oqtopus-team/qdash/issues/new?template=BUG_REPORT.yaml",
    );
    expect(screen.getByText(/QDash does not file issues/)).toBeInTheDocument();
  });

  it("offers no report for a refused or correctable request, or an older error", () => {
    renderError("Error: HTTP 422: policy.quality_gates: name each gate's task");
    expect(screen.queryByRole("button", { name: "Report this error" })).toBeNull();
    cleanup();
    renderError("Error: HTTP 500: boom", false);
    expect(screen.queryByRole("button", { name: "Report this error" })).toBeNull();
  });
});

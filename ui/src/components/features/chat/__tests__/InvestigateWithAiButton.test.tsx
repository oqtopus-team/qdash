import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { InvestigateWithAiButton } from "../InvestigateWithAiButton";

const investigate = vi.fn();
let dock: { investigate: typeof investigate } | null = { investigate };

vi.mock("@/contexts/ChatDockContext", () => ({
  useOptionalChatDock: () => dock,
}));

afterEach(() => {
  cleanup();
  investigate.mockClear();
  dock = { investigate };
});

describe("InvestigateWithAiButton", () => {
  it("starts the investigation on the chosen surface without selecting the card around it", () => {
    const onCardClick = vi.fn();
    const target = { executionId: "exec-1", taskId: "task-1" };
    render(
      <div onClick={onCardClick}>
        <InvestigateWithAiButton target={target} surface="mini" />
      </div>,
    );

    fireEvent.click(screen.getByRole("button", { name: "Investigate with AI" }));

    expect(investigate).toHaveBeenCalledTimes(1);
    expect(investigate).toHaveBeenCalledWith(target, "mini");
    expect(onCardClick).not.toHaveBeenCalled();
  });

  it("renders nothing without an execution or without the chat dock", () => {
    const { container, rerender } = render(<InvestigateWithAiButton target={null} />);
    expect(container.innerHTML).toBe("");

    dock = null;
    rerender(<InvestigateWithAiButton target={{ executionId: "exec-1" }} />);
    expect(container.innerHTML).toBe("");
  });
});

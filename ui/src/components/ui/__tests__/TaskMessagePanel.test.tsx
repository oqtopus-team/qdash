import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { TaskMessagePanel } from "@/components/ui/TaskMessagePanel";

describe("TaskMessagePanel", () => {
  afterEach(() => cleanup());

  it("labels a failed task's message as an error log", () => {
    render(<TaskMessagePanel status="failed" message="qubit_frequency was not resolved" />);

    expect(screen.queryByText("Error Log")).not.toBeNull();
    expect(screen.queryByText("qubit_frequency was not resolved")).not.toBeNull();
  });

  it("shows a completed task's message without error styling", () => {
    render(<TaskMessagePanel status="completed" message="CheckFineChevron is completed" />);

    expect(screen.queryByText("Error Log")).toBeNull();
    expect(screen.queryByText("Message")).not.toBeNull();
    expect(screen.queryByText("CheckFineChevron is completed")).not.toBeNull();
  });

  it("renders nothing when the message is blank", () => {
    const { container } = render(<TaskMessagePanel status="completed" message="   " />);

    expect(container.innerHTML).toBe("");
  });

  it("renders nothing when a failed task has no message and no fallback is requested", () => {
    const { container } = render(<TaskMessagePanel status="failed" message={null} />);

    expect(container.innerHTML).toBe("");
  });

  it("falls back to a placeholder for a failed task without a message", () => {
    render(<TaskMessagePanel status="failed" message={null} showEmptyFallback />);

    expect(screen.queryByText("No error message recorded.")).not.toBeNull();
  });

  it("keeps the fallback out of non-failed statuses", () => {
    const { container } = render(
      <TaskMessagePanel status="completed" message={null} showEmptyFallback />,
    );

    expect(container.innerHTML).toBe("");
  });

  it("renders a copyable stack trace when one is present", () => {
    render(
      <TaskMessagePanel status="failed" message="boom" stackTrace="Traceback (most recent call)" />,
    );

    expect(screen.queryByText("Stack Trace")).not.toBeNull();
    expect(screen.queryByText("Traceback (most recent call)")).not.toBeNull();
    expect(screen.queryByRole("button", { name: "Copy" })).not.toBeNull();
  });
});

import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ExecutionTaskProgress } from "@/components/features/execution/ExecutionTaskProgress";

describe("ExecutionTaskProgress", () => {
  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it("shows measured progress and remaining time for a running task", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-27T09:00:05Z"));

    render(
      <ExecutionTaskProgress
        status="running"
        note={{
          progress: {
            current: 4,
            total: 12,
            description: "control power sweep for Q00",
            elapsed_seconds: 20,
            eta_seconds: 40,
            updated_at: "2026-08-27T09:00:00Z",
          },
        }}
      />,
    );

    expect(screen.getByText("control power sweep for Q00")).toBeTruthy();
    expect(screen.getByText("4 / 12")).toBeTruthy();
    expect(screen.getByText("Estimated 35s remaining in this phase")).toBeTruthy();
    expect(screen.getByRole("progressbar").getAttribute("aria-label")).toBe("33% complete");
  });

  it("does not show stale progress for a completed task", () => {
    render(
      <ExecutionTaskProgress
        status="completed"
        note={{
          progress: {
            current: 12,
            total: 12,
            description: "control power sweep for Q00",
            eta_seconds: 0,
            updated_at: "2026-08-27T09:00:00Z",
          },
        }}
      />,
    );

    expect(screen.queryByLabelText("Task progress")).toBeNull();
  });

  it("warns that another sweep may follow and shows completed sweeps", () => {
    render(
      <ExecutionTaskProgress
        status="running"
        note={{
          progress: {
            current: 1,
            total: 10,
            description: "Chevron sweep",
            eta_seconds: null,
            updated_at: new Date().toISOString(),
            phase: 2,
            has_multiple_phases: true,
            phase_total_min: 4,
            phase_total_max: 4,
          },
        }}
      />,
    );

    expect(screen.getByText("Sweep 2 / 4")).toBeTruthy();
    expect(screen.getByText("1 sweep completed")).toBeTruthy();
    expect(screen.getByText("Progress includes all planned sweeps.")).toBeTruthy();
    expect(screen.getByRole("progressbar").getAttribute("aria-label")).toBe("28% of task complete");
  });

  it("shows honest phase-count bounds for an adaptive task", () => {
    render(
      <ExecutionTaskProgress
        status="running"
        note={{
          progress: {
            current: 5,
            total: 10,
            description: "Chevron sweep",
            eta_seconds: null,
            updated_at: new Date().toISOString(),
            phase: 1,
            has_multiple_phases: true,
            phase_total_min: 2,
            phase_total_max: 4,
          },
        }}
      />,
    );

    expect(screen.getByText("Sweep 1 / 2–4")).toBeTruthy();
    expect(screen.getByText("This adaptive task will run 2 to 4 sweeps in total.")).toBeTruthy();
    expect(screen.getByRole("progressbar").getAttribute("aria-label")).toBe("50% complete");
  });
});

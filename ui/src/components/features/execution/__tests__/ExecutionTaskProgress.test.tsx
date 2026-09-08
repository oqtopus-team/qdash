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
    expect(screen.getByText("4 / 12 points")).toBeTruthy();
    expect(screen.getByText("This measurement · ~35s remaining")).toBeTruthy();
    expect(screen.getByText("33%")).toBeTruthy();
    expect(screen.getByRole("progressbar", { name: "Measurement progress" })).toHaveAttribute(
      "value",
      String((4 / 12) * 100),
    );
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

  it("uses completed sweep counts for all-sweep progress", () => {
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

    expect(screen.getByText("1 / 4 sweeps completed")).toBeTruthy();
    expect(screen.queryByText(/1 \/ 10 points/)).toBeNull();
    expect(screen.getByText("28%")).toBeTruthy();
    expect(
      Number(screen.getByRole("progressbar", { name: "All sweeps" }).getAttribute("value")),
    ).toBeCloseTo(27.5);
  });

  it("shows whole-search ETA and hides the inner Rabi time-point count", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-27T09:00:05Z"));
    render(
      <ExecutionTaskProgress
        status="running"
        note={{
          progress: {
            current: 13,
            total: 26,
            phase: 7,
            has_multiple_phases: true,
            phase_total_min: 65,
            phase_total_max: 65,
            eta_seconds: 10,
            overall_eta_seconds: 1200,
            updated_at: "2026-08-27T09:00:00Z",
          },
        }}
      />,
    );
    expect(screen.getByText("6 / 65 sweeps completed")).toBeTruthy();
    expect(screen.getByText("All sweeps · ~19m 55s remaining")).toBeTruthy();
    expect(screen.getByText("10%")).toBeTruthy();
    expect(screen.queryByText(/13 \/ 26/)).toBeNull();
    expect(screen.queryByText(/This sweep/)).toBeNull();
  });

  it("does not substitute per-sweep ETA when the total estimate is unavailable", () => {
    render(
      <ExecutionTaskProgress
        status="running"
        note={{
          progress: {
            current: 13,
            total: 26,
            phase: 1,
            has_multiple_phases: true,
            phase_total_min: 65,
            phase_total_max: 65,
            eta_seconds: 10,
            updated_at: new Date().toISOString(),
          },
        }}
      />,
    );
    expect(screen.getByText("0 / 65 sweeps completed")).toBeTruthy();
    expect(screen.getByText("Estimating remaining time for all sweeps…")).toBeTruthy();
    expect(screen.queryByText(/This sweep/)).toBeNull();
  });

  it.each([25, 26])(
    "does not announce completion before the last time point (%i / 26)",
    (current) => {
      render(
        <ExecutionTaskProgress
          status="running"
          note={{
            progress: {
              current,
              total: 26,
              phase: 65,
              has_multiple_phases: true,
              phase_total_min: 65,
              phase_total_max: 65,
              overall_eta_seconds: current === 26 ? 0 : 2,
              updated_at: new Date().toISOString(),
            },
          }}
        />,
      );
      expect(screen.getByText(`${current === 26 ? 65 : 64} / 65 sweeps completed`)).toBeTruthy();
      expect(screen.getByText(current === 26 ? "100%" : "99%")).toBeTruthy();
      if (current === 26) expect(screen.getByText("Finishing measurement…")).toBeTruthy();
    },
  );

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
    expect(screen.getByRole("progressbar", { name: "Current sweep" })).toHaveAttribute(
      "value",
      "50",
    );
  });

  it.each(["pending", "scheduled", "running"])(
    "shows an explicit waiting state for %s without measurement progress",
    (status) => {
      render(<ExecutionTaskProgress status={status} />);
      expect(screen.getByRole("status")).toHaveTextContent(
        status === "running" ? "Preparing measurement" : "Waiting to start",
      );
      expect(screen.queryByRole("progressbar")).toBeNull();
    },
  );

  it("shows the measured count without inventing a percentage when the total is unknown", () => {
    render(
      <ExecutionTaskProgress
        status="running"
        note={{
          progress: { current: 7, total: null, updated_at: new Date().toISOString() },
        }}
      />,
    );
    expect(screen.getByText("7 points measured")).toBeTruthy();
    expect(screen.getByText("Measuring · total count unavailable")).toBeTruthy();
    expect(screen.queryByRole("progressbar")).toBeNull();
  });

  it("does not show zero seconds remaining when a running measurement outlasts its estimate", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-08-27T09:01:00Z"));
    render(
      <ExecutionTaskProgress
        status="running"
        note={{
          progress: {
            current: 4,
            total: 12,
            eta_seconds: 10,
            updated_at: "2026-08-27T09:00:00Z",
          },
        }}
      />,
    );
    expect(screen.getByText("Updating time estimate…")).toBeTruthy();
  });
});

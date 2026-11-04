import { cleanup, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { HomePageContent } from "@/components/features/home/HomePageContent";

const mockExecutionActivity = vi.hoisted(() => vi.fn());
const mockChips = vi.hoisted(() => vi.fn());
const mockTaskResults = vi.hoisted(() => vi.fn());
const mockSchedules = vi.hoisted(() => vi.fn());
const mockProject = vi.hoisted(() => vi.fn());

// Only the activity hook is provided: the page must not poll the lock or a running execution,
// since the global execution indicator already shows progress.
vi.mock("@/client/execution/execution", () => ({
  getGetExecutionActivityQueryKey: () => ["/executions/activity"],
  useGetExecutionActivity: mockExecutionActivity,
}));

vi.mock("@/contexts/ThemeContext", () => ({ useIsDarkTheme: () => false }));

function day(date: string, counts: Partial<Record<string, number>> = {}) {
  const merged = { completed: 0, failed: 0, running: 0, scheduled: 0, cancelled: 0, other: 0 };
  Object.assign(merged, counts);
  return { date, ...merged, total: Object.values(merged).reduce((a, b) => a + b, 0) };
}

vi.mock("@/client/chip/chip", () => ({
  useListChips: mockChips,
}));

vi.mock("@/client/task-result/task-result", () => ({
  useListTaskResults: mockTaskResults,
}));

vi.mock("@/client/flow/flow", () => ({
  useListAllFlowSchedules: mockSchedules,
}));

vi.mock("@/contexts/ProjectContext", () => ({
  useProject: mockProject,
}));

const NOW = new Date("2026-11-04T00:00:00Z");

function scheduledRun(flowName: string, hoursFromNow: number | null, extra: object = {}) {
  return {
    schedule_id: `run-${flowName}`,
    flow_name: flowName,
    schedule_type: "one-time",
    cron: null,
    next_run:
      hoursFromNow === null
        ? null
        : new Date(NOW.getTime() + hoursFromNow * 60 * 60 * 1000).toISOString(),
    active: true,
    created_at: "2026-11-01T00:00:00Z",
    chip_id: "chip-1",
    ...extra,
  };
}

function upcomingFlowNames(): string[] {
  const list = screen.getByRole("list", { name: "Upcoming runs" });
  return within(list)
    .getAllByRole("listitem")
    .map((item) => item.querySelector(".font-medium")?.textContent ?? "");
}

describe("HomePageContent", () => {
  beforeEach(() => {
    vi.useFakeTimers({ toFake: ["Date"] });
    vi.setSystemTime(NOW);
    mockProject.mockReturnValue({ canEdit: true, projectId: "project-1" });
    mockSchedules.mockReturnValue({
      data: { data: { schedules: [] } },
      isLoading: false,
      error: null,
    });
    mockChips.mockReturnValue({
      data: { data: { chips: [{ chip_id: "chip-1" }] } },
      isLoading: false,
      error: null,
    });
    mockExecutionActivity.mockReturnValue({
      data: {
        data: {
          chip_id: null,
          days: 30,
          timezone: "Asia/Tokyo",
          since: "2026-10-04",
          until: "2026-11-02",
          buckets: [day("2026-11-01", { completed: 2 }), day("2026-11-02", { failed: 1 })],
        },
      },
      isLoading: false,
      isError: false,
    });
    mockTaskResults.mockReturnValue({
      data: {
        data: {
          items: [
            {
              task_id: "task-1",
              task_name: "CheckRabi",
              qid: "Q0",
              chip_id: "chip-1",
              status: "failed",
              execution_id: "execution-1",
              message: "Fit failed",
            },
          ],
        },
      },
      isLoading: false,
      error: null,
    });
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    vi.useRealTimers();
  });

  it("summarizes active work and items that need attention", () => {
    render(<HomePageContent />);

    expect(screen.getByRole("heading", { name: "Home" })).toBeTruthy();
    expect(screen.getByRole("heading", { name: "Executions" })).toBeTruthy();
    expect(screen.getByTestId("home-activity-total")).toHaveTextContent("3executions · 1 failed");
    expect(screen.getByText("CheckRabi")).toBeTruthy();
    expect(screen.queryByText("Recent notifications")).toBeNull();
    expect(screen.getByRole("link", { name: /Run a task/ }).getAttribute("href")).toBe("/tasks");
    expect(screen.queryByRole("link", { name: /View inbox/ })).toBeNull();
    expect(screen.getByRole("link", { name: "Setup tour" }).getAttribute("href")).toBe(
      "/chip?tutorial=create-chip",
    );
  });

  it("keeps quick actions single column until the layout breakpoints", () => {
    const { container } = render(<HomePageContent />);

    const quickActions = container.querySelector("[aria-labelledby='quick-actions-heading'] > div");
    expect(quickActions?.className).toContain("grid-cols-1");
  });

  it("places upcoming runs between executions and needs attention", () => {
    render(<HomePageContent />);

    const currentExecution = screen.getByRole("heading", { name: "Executions" });
    const upcomingRuns = screen.getByRole("heading", { name: "Upcoming runs" });
    const needsAttention = screen.getByRole("heading", { name: "Needs attention" });
    expect(
      currentExecution.compareDocumentPosition(upcomingRuns) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
    expect(
      upcomingRuns.compareDocumentPosition(needsAttention) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it("lists the next five scheduled runs soonest first", () => {
    mockSchedules.mockReturnValue({
      data: {
        data: {
          schedules: [
            scheduledRun("flow-f", 30),
            scheduledRun("flow-c", 3),
            scheduledRun("flow-a", 1, { chip_id: "chip-9" }),
            scheduledRun("flow-e", 5),
            scheduledRun("flow-b", 2),
            scheduledRun("flow-d", 4),
          ],
        },
      },
      isLoading: false,
      error: null,
    });

    render(<HomePageContent />);

    expect(upcomingFlowNames()).toEqual(["flow-a", "flow-b", "flow-c", "flow-d", "flow-e"]);
    const firstRun = screen.getByRole("link", { name: /flow-a/ });
    expect(firstRun.getAttribute("href")).toBe("/workflow/flow-a");
    expect(within(firstRun).getByText("chip-9")).toBeTruthy();
    expect(within(firstRun).getByText("2026-11-04 10:00")).toBeTruthy();
    expect(within(firstRun).getByText("in 1h")).toBeTruthy();
  });

  it("excludes paused schedules and schedule definitions without a run", () => {
    mockSchedules.mockReturnValue({
      data: {
        data: {
          schedules: [
            scheduledRun("paused-flow", 1, { active: false }),
            scheduledRun("cron-definition", null, { schedule_type: "cron", cron: "0 2 * * *" }),
            scheduledRun("past-flow", -1),
            scheduledRun("active-flow", 2),
          ],
        },
      },
      isLoading: false,
      error: null,
    });

    render(<HomePageContent />);

    expect(upcomingFlowNames()).toEqual(["active-flow"]);
  });

  it("shows a compact empty state when nothing is scheduled", () => {
    render(<HomePageContent />);

    expect(screen.getByText("No upcoming scheduled runs.")).toBeTruthy();
    expect(screen.queryByRole("list", { name: "Upcoming runs" })).toBeNull();
  });

  it("reports when scheduled runs cannot be loaded", () => {
    mockSchedules.mockReturnValue({
      data: undefined,
      isLoading: false,
      error: new Error("Network Error"),
    });

    render(<HomePageContent />);

    expect(screen.getByText("Failed to load scheduled runs.")).toBeTruthy();
    expect(screen.getByText("CheckRabi")).toBeTruthy();
  });

  it("shows upcoming runs without workflow links for read-only members", () => {
    mockProject.mockReturnValue({ canEdit: false });
    mockSchedules.mockReturnValue({
      data: { data: { schedules: [scheduledRun("flow-a", 1)] } },
      isLoading: false,
      error: null,
    });

    render(<HomePageContent />);

    expect(upcomingFlowNames()).toEqual(["flow-a"]);
    expect(screen.queryByRole("link", { name: /flow-a/ })).toBeNull();
    expect(screen.queryByRole("link", { name: /All workflows/ })).toBeNull();
  });

  it("shows calm empty states when no work is waiting", () => {
    mockExecutionActivity.mockReturnValue({
      data: { data: { buckets: [day("2026-11-02")] } },
      isLoading: false,
      isError: false,
    });
    mockTaskResults.mockReturnValue({
      data: { data: { items: [] } },
      isLoading: false,
      error: null,
    });
    render(<HomePageContent />);

    expect(screen.getByText("No executions in the last 30 days")).toBeTruthy();
    expect(screen.getByText("No failed task results")).toBeTruthy();
  });

  it("prominently offers setup when the project has no chips", () => {
    mockChips.mockReturnValue({
      data: { data: { chips: [] } },
      isLoading: false,
      error: null,
    });

    render(<HomePageContent />);

    expect(screen.getByRole("heading", { name: "Create your first chip" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Start setup tour" }).getAttribute("href")).toBe(
      "/chip?tutorial=create-chip",
    );
    expect(screen.queryByRole("link", { name: "Setup tour" })).toBeNull();
  });

  it("replaces the current execution card with project-wide activity", () => {
    render(<HomePageContent />);

    expect(mockExecutionActivity).toHaveBeenCalled();
    const [params] = mockExecutionActivity.mock.calls[0];
    expect(params).toEqual({ days: 30, timezone: expect.any(String) });
    expect(params).not.toHaveProperty("chip_id");
    expect(screen.queryByRole("heading", { name: "Current execution" })).toBeNull();
    expect(screen.queryByText(/tasks$/)).toBeNull();
    expect(screen.getByRole("link", { name: /All executions/ }).getAttribute("href")).toBe(
      "/execution",
    );
    expect(screen.getByRole("heading", { name: "Needs attention" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Recent notifications" })).toBeNull();
  });
});

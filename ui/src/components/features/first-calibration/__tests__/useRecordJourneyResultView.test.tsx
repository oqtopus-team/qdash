import { act, cleanup, render } from "@testing-library/react";
import { StrictMode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useRecordJourneyResultView } from "@/components/features/first-calibration/useRecordJourneyResultView";
import { journeyStorageKey } from "@/lib/firstCalibrationJourney";

const project = vi.hoisted(() => ({ projectId: "project-1", canEdit: true }));
const execution = vi.hoisted(() => ({
  calls: [] as {
    executionId: string;
    queryKey: readonly unknown[];
    enabled: boolean;
  }[],
  tasks: [{ task_id: "t1", status: "completed" }] as {
    task_id: string;
    status: string;
  }[],
  /** The read of the journey's execution failed: no data. */
  failed: false,
}));

// The journey's execution, as read in the current project's scope.
vi.mock("@/client/execution/execution", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  useGetExecution: (
    executionId: string,
    options: { query: { queryKey: readonly unknown[]; enabled: boolean } },
  ) => {
    execution.calls.push({ executionId, ...options.query });
    return {
      data:
        options.query.enabled && !execution.failed
          ? { data: { execution_id: executionId, task: execution.tasks } }
          : undefined,
    };
  },
}));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ username: "alice" }),
}));

vi.mock("@/contexts/ProjectContext", () => ({
  useProject: () => project,
}));

const KEY = journeyStorageKey("alice", "project-1");

type Result = { task_id: string; execution_id: string; status: string };

function Viewer({ result }: { result: Result | null }) {
  useRecordJourneyResultView(result);
  return null;
}

function stored() {
  return JSON.parse(window.localStorage.getItem(KEY) ?? "null");
}

function patchStored(patch: Record<string, unknown>) {
  window.localStorage.setItem(KEY, JSON.stringify({ ...stored(), ...patch }));
}

const T1: Result = { task_id: "t1", execution_id: "20261105-001", status: "completed" };

/** Let a pending leave run; leaving is decided a tick after the view ends. */
async function settle() {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

/** Open a result, then end its view the given way. */
async function openThenLeave(result: Result, leave: "close" | "unmount" = "close") {
  const view = render(<Viewer result={result} />);
  await settle();
  if (leave === "close") view.rerender(<Viewer result={null} />);
  else view.unmount();
  await settle();
}

describe("useRecordJourneyResultView", () => {
  beforeEach(() => {
    project.canEdit = true;
    project.projectId = "project-1";
    execution.calls = [];
    execution.tasks = [{ task_id: "t1", status: "completed" }];
    execution.failed = false;
    window.localStorage.setItem(
      KEY,
      JSON.stringify({
        version: 1,
        status: "active",
        chipId: "chip-a",
        flowName: "first_calibration",
        executionId: "20261105-001",
        hardwareConfirmedChipId: null,
        inspectedTaskId: null,
        chipOverviewSeen: false,
        startedAt: "2026-11-05T00:00:00.000Z",
        updatedAt: "2026-11-05T00:00:00.000Z",
      }),
    );
  });

  afterEach(async () => {
    cleanup();
    // A view the cleanup closed decides on leaving a tick later; let it finish here.
    await new Promise((resolve) => setTimeout(resolve, 0));
    window.localStorage.clear();
  });

  it("keeps the result step while the result is open and records it once the view closes", async () => {
    const view = render(<Viewer result={T1} />);
    await settle();
    expect(stored().inspectedTaskId).toBeNull();

    view.rerender(<Viewer result={null} />);
    await settle();
    expect(stored().inspectedTaskId).toBe("t1");
  });

  it("records the result when its page is left", async () => {
    await openThenLeave(T1, "unmount");
    expect(stored().inspectedTaskId).toBe("t1");
  });

  it("records the first result when the view moves on to another one", async () => {
    execution.tasks = [
      { task_id: "t1", status: "completed" },
      { task_id: "t2", status: "completed" },
    ];
    const view = render(<Viewer result={T1} />);
    await settle();
    view.rerender(<Viewer result={{ ...T1, task_id: "t2" }} />);
    await settle();
    expect(stored().inspectedTaskId).toBe("t1");
  });

  it("does not count React's development remount as leaving the result", async () => {
    render(
      <StrictMode>
        <Viewer result={T1} />
      </StrictMode>,
    );
    await settle();
    expect(stored().inspectedTaskId).toBeNull();
  });

  it.each([
    ["another execution", { task_id: "t9", execution_id: "20261104-007", status: "completed" }],
    ["a failed result", { task_id: "t2", execution_id: "20261105-001", status: "failed" }],
    ["a running result", { task_id: "t3", execution_id: "20261105-001", status: "running" }],
  ])("ignores %s", async (_label, result) => {
    await openThenLeave(result);
    expect(stored().inspectedTaskId).toBeNull();
  });

  it("does not record a result whose run could not be read", async () => {
    execution.failed = true;
    await openThenLeave(T1);
    expect(stored().inspectedTaskId).toBeNull();
  });

  it("reads the journey's execution in the current user and project", () => {
    render(<Viewer result={T1} />);
    const call = execution.calls.find((item) => item.enabled);
    expect(call?.executionId).toBe("20261105-001");
    expect(call?.queryKey).toEqual([
      "/executions/20261105-001",
      { firstCalibration: { username: "alice", projectId: "project-1" } },
    ]);
  });

  it("ignores a cached result of another project that reuses the journey's execution id", async () => {
    // The result on screen says it belongs to 20261105-001, but this project's run of that id
    // never had task t-other: it was cached in another project.
    await openThenLeave({ ...T1, task_id: "t-other" });
    expect(stored().inspectedTaskId).toBeNull();
  });

  it("waits until this project's run lists the task as completed", async () => {
    execution.tasks = [{ task_id: "t1", status: "running" }];
    await openThenLeave(T1);
    expect(stored().inspectedTaskId).toBeNull();
  });

  it("does not move a journey paused while the result was open", async () => {
    const view = render(<Viewer result={T1} />);
    await settle();
    act(() => patchStored({ status: "paused" }));
    window.dispatchEvent(new StorageEvent("storage", { key: KEY }));
    view.rerender(<Viewer result={null} />);
    await settle();
    expect(stored()).toMatchObject({ status: "paused", inspectedTaskId: null });
  });

  it("keeps the result the guide recorded when its explanation ended", async () => {
    execution.tasks = [
      { task_id: "t1", status: "completed" },
      { task_id: "t2", status: "completed" },
    ];
    const view = render(<Viewer result={{ ...T1, task_id: "t2" }} />);
    await settle();
    // The guide finished explaining t1 while t2 was open.
    act(() => {
      patchStored({ inspectedTaskId: "t1" });
      window.dispatchEvent(new StorageEvent("storage", { key: KEY }));
    });
    view.rerender(<Viewer result={null} />);
    await settle();
    expect(stored().inspectedTaskId).toBe("t1");
  });

  it("records nothing for a viewer", async () => {
    project.canEdit = false;
    await openThenLeave(T1);
    expect(stored().inspectedTaskId).toBeNull();
  });
});

import { useState } from "react";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ExecutionPageContent } from "@/components/features/execution/ExecutionPageContent";

let loadingNextPage = false;
const DEFAULT_DETAIL = { note: { flow_run_id: "flow-123" }, task: [] };
let executionDetail: Record<string, unknown> = DEFAULT_DETAIL;
const mockInvestigate = vi.fn();
const mockCancelMutate = vi.fn();
const mockToastSuccess = vi.fn();
const mockToastError = vi.fn();
const mockInvalidateQueries = vi.fn();

vi.mock("@tanstack/react-query", async () => {
  const actual =
    await vi.importActual<typeof import("@tanstack/react-query")>("@tanstack/react-query");
  return {
    ...actual,
    useQueryClient: () => ({ invalidateQueries: mockInvalidateQueries }),
  };
});

vi.mock("@/client/chip/chip", () => ({
  useListChips: () => ({
    data: {
      data: {
        chips: [{ chip_id: "chip-1", installed_at: "2026-06-01T00:00:00Z" }],
      },
    },
  }),
}));

type ListArgs = { skip: number; chip_id: string; date?: string };

function flatExecutions({ skip, chip_id, date }: ListArgs) {
  return {
    total: date ? 0 : 40,
    executions: date
      ? [] // the API returns nothing for a day with no runs
      : skip > 0 || chip_id === "chip-2"
        ? [
            {
              execution_id: "exec-3",
              name: "Other Execution",
              status: "completed",
              start_at: "2026-06-02T00:00:00Z",
            },
          ]
        : [
            {
              execution_id: "exec-1",
              name: "Running Execution",
              status: "running",
              start_at: "2026-06-01T00:00:00Z",
              elapsed_time: "1m",
              username: "tester",
            },
            {
              execution_id: "exec-2",
              name: "Completed Execution",
              status: "completed",
              start_at: "2026-06-01T00:00:00Z",
              username: "tester",
            },
          ],
  };
}

// Rows the grouped list returns; null means "the flat rows, none grouped".
let groupedItems: Record<string, unknown>[] | null = null;
let groupedSummary: Record<string, number> = {
  total: 0,
  total_executions: 0,
  grouped_executions: 0,
  agent_sessions: 0,
};
let groupedError = false;
let currentProjectId = "project-1";
const mockListExecutions = vi.fn();
const mockListGroups = vi.fn();

vi.mock("@/contexts/ProjectContext", () => ({
  useProject: () => ({ projectId: currentProjectId }),
}));

vi.mock("@/client/execution/execution", () => ({
  useListExecutions: (args: ListArgs, options: { query: { enabled: boolean } }) => {
    mockListExecutions(args, options);
    return {
      data: { data: flatExecutions(args) },
      isError: false,
      isLoading: args.skip > 0 && loadingNextPage,
    };
  },
  useListExecutionGroups: (args: ListArgs, options: { query: { enabled: boolean } }) => {
    mockListGroups(args, options);
    const flat = flatExecutions(args);
    const items =
      groupedItems ??
      flat.executions.map((execution) => ({
        kind: "execution",
        execution,
        children: [],
        children_total: 0,
        children_in_filter: 0,
        children_omitted: 0,
      }));
    return {
      data: {
        data: groupedItems
          ? { items, skip: args.skip, limit: 20, children_limit: 20, ...groupedSummary }
          : {
              items,
              total: flat.total,
              total_executions: flat.total,
              grouped_executions: 0,
              agent_sessions: 0,
              skip: args.skip,
              limit: 20,
              children_limit: 20,
            },
      },
      isError: groupedError,
      isLoading: args.skip > 0 && loadingNextPage,
    };
  },
  useGetExecution: () => ({
    data: { data: executionDetail },
    isLoading: false,
    isError: false,
  }),
  useCancelExecution: () => ({
    mutate: mockCancelMutate,
    isPending: false,
    isError: false,
    isSuccess: false,
    error: null,
  }),
  getListExecutionsQueryKey: () => ["/executions"],
  getListExecutionGroupsQueryKey: () => ["/executions/groups"],
  getGetExecutionQueryKey: (executionId: string) => [`/executions/${executionId}`],
}));

vi.mock("@/contexts/ChatDockContext", () => ({
  useOptionalChatDock: () => ({ investigate: mockInvestigate }),
}));

vi.mock("@/hooks/useDateNavigation", () => ({
  useDateNavigation: () => undefined,
}));

vi.mock("@/hooks/useUrlState", () => ({
  useExecutionUrlState: () => {
    const [selectedChip, setSelectedChip] = useState("chip-1");
    return { selectedChip, setSelectedChip, isInitialized: true };
  },
}));

vi.mock("@/components/ui/Toast", () => ({
  useToast: () => ({
    success: mockToastSuccess,
    error: mockToastError,
    info: vi.fn(),
    warning: vi.fn(),
  }),
}));

vi.mock("next/link", () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

vi.mock("@/components/features/execution/ExecutionActivityChart", () => ({
  DEFAULT_ACTIVITY_WINDOW: 30,
  ExecutionActivityChart: ({
    days,
    selectedDate,
    onDateSelect,
  }: {
    days: number;
    selectedDate: string;
    onDateSelect: (date: string) => void;
  }) => (
    <div>
      <span>ActivityChart {days}d</span>
      <span>selected:{selectedDate}</span>
      <button type="button" onClick={() => onDateSelect("20260101")}>
        pick-day
      </button>
    </div>
  ),
}));

vi.mock("@/components/charts/TaskFigure", () => ({
  TaskFigure: () => <div>TaskFigure</div>,
}));

vi.mock("@/components/selectors/ChipSelector", () => ({
  ChipSelector: ({ onChipSelect }: { onChipSelect: (chip: string) => void }) => (
    <button onClick={() => onChipSelect("chip-2")}>Change chip</button>
  ),
}));

vi.mock("@/components/selectors/DateSelector", () => ({
  DateSelector: ({ onDateSelect }: { onDateSelect: (date: string) => void }) => (
    <button onClick={() => onDateSelect("20260602")}>Change date</button>
  ),
}));

vi.mock("@/components/ui/PageContainer", () => ({
  PageContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock("@/components/ui/PageFiltersBar", () => ({
  PageFiltersBar: Object.assign(
    ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
    {
      Group: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
      Item: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
    },
  ),
}));

vi.mock("@/components/ui/PageHeader", () => ({
  PageHeader: ({ title }: { title: string }) => <h1>{title}</h1>,
}));

vi.mock("@/components/ui/Skeleton/PageSkeletons", () => ({
  ExecutionPageSkeleton: () => <div>Skeleton</div>,
}));

function openSidebarAndClickCancel() {
  // Open the sidebar for the running execution.
  fireEvent.click(screen.getByText("Running Execution"));
  // Click the list-page Cancel button inside the sidebar.
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
}

describe("ExecutionPageContent cancel confirmation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    loadingNextPage = false;
    executionDetail = DEFAULT_DETAIL;
    // Reset the mutate implementation so callback-driven tests don't leak into others.
    mockCancelMutate.mockReset();
  });

  afterEach(() => {
    cleanup();
  });

  it("does not cancel immediately but shows a confirmation dialog when Cancel is clicked", () => {
    render(<ExecutionPageContent />);

    openSidebarAndClickCancel();

    // The project-specific confirmation dialog is shown.
    expect(
      screen.getByText(
        "Are you sure you want to cancel this execution? This action cannot be undone.",
      ),
    ).toBeTruthy();
    // The cancellation is NOT triggered until the user confirms.
    expect(mockCancelMutate).not.toHaveBeenCalled();
  });

  it("shows the activity chart and lets it pick the day filter", () => {
    render(<ExecutionPageContent />);

    expect(screen.getByText("ActivityChart 30d")).toBeTruthy();
    expect(screen.getByText("selected:latest")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "pick-day" }));

    expect(screen.getByText("selected:20260101")).toBeTruthy();
  });

  it("opens a non-modal details panel", () => {
    render(<ExecutionPageContent />);

    fireEvent.click(screen.getByText("Running Execution"));

    const panel = screen.getByRole("complementary", { name: "Execution details" });
    expect(panel.getAttribute("aria-hidden")).toBe("false");

    fireEvent.keyDown(document, { key: "Escape" });
    expect(panel.getAttribute("aria-hidden")).toBe("true");
  });

  it("links the details panel to the execution's calibration session in this project", () => {
    executionDetail = {
      ...DEFAULT_DETAIL,
      calibration_session: {
        calibration_session_id: "cs-1",
        chip_id: "chip-1",
        objective: "Bring up qubits",
        status: "open",
        via: "pipeline_run",
        pipeline_run_id: "cpr-1",
      },
    };
    render(<ExecutionPageContent />);
    fireEvent.click(screen.getByText("Running Execution"));
    const panel = screen.getByRole("complementary", { name: "Execution details" });
    expect(
      within(panel).getByRole("link", { name: "Open calibration session" }).getAttribute("href"),
    ).toBe("/calibration-sessions/cs-1?project=project-1");
  });

  it("shows no calibration notice for an ordinary execution", () => {
    render(<ExecutionPageContent />);
    fireEvent.click(screen.getByText("Running Execution"));
    expect(screen.queryByTestId("execution-calibration-notice")).toBeNull();
  });

  it("browses adjacent executions without closing the panel and resets its scroll", () => {
    render(<ExecutionPageContent />);
    fireEvent.click(screen.getByText("Running Execution"));
    const panel = screen.getByRole("complementary", { name: "Execution details" });
    const previous = within(panel).getByRole("button", {
      name: "Previous execution",
    }) as HTMLButtonElement;
    const next = within(panel).getByRole("button", { name: "Next execution" }) as HTMLButtonElement;
    expect(previous.disabled).toBe(true);
    expect(next.disabled).toBe(false);
    expect(within(panel).getByText("1 of 2 on this page")).toBeTruthy();

    panel.scrollTop = 300;
    fireEvent.click(next);
    expect(panel.scrollTop).toBe(0);
    expect(within(panel).getByRole("heading", { name: "Completed Execution" })).toBeTruthy();
    expect(within(panel).getByRole("link", { name: "View Details" }).getAttribute("href")).toBe(
      "/execution/chip-1/exec-2",
    );
    expect(within(panel).getByText("2 of 2 on this page")).toBeTruthy();
    expect(next.disabled).toBe(true);
    expect(previous.disabled).toBe(false);
    expect(within(panel).queryByRole("button", { name: "Cancel" })).toBeNull();

    fireEvent.click(previous);
    expect(within(panel).getByRole("heading", { name: "Running Execution" })).toBeTruthy();
  });

  it("moves focus into the panel and returns it to the last viewed execution on close", () => {
    render(<ExecutionPageContent />);
    const firstCard = screen.getByRole("button", {
      name: "View Running Execution execution details",
    });
    firstCard.focus();
    fireEvent.keyDown(firstCard, { key: "Enter" });
    expect(document.activeElement).toBe(
      screen.getByRole("button", { name: "Close execution details" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Next execution" }));
    fireEvent.keyDown(document, { key: "Escape" });
    const lastCard = screen.getByRole("button", {
      name: "View Completed Execution execution details",
    });
    expect(document.activeElement).toBe(lastCard);
    expect(lastCard.getAttribute("aria-expanded")).toBe("false");
    expect(document.getElementById("execution-details-panel")?.hasAttribute("inert")).toBe(true);
  });

  it.each(["Change chip", "Next"])(
    "restores focus after %s replaces the execution list",
    (name) => {
      render(<ExecutionPageContent />);
      fireEvent.click(screen.getByText("Running Execution"));
      const panel = screen.getByRole("complementary", { name: "Execution details" });
      panel.scrollTop = 300;
      fireEvent.click(screen.getByRole("button", { name }));
      expect(document.activeElement).toBe(
        screen.getByRole("button", { name: "View Other Execution execution details" }),
      );
      expect(panel.scrollTop).toBe(0);
      expect(panel.getAttribute("aria-hidden")).toBe("true");
    },
  );

  it("waits for the new page to load before restoring focus", () => {
    loadingNextPage = true;
    const { rerender } = render(<ExecutionPageContent />);
    fireEvent.click(screen.getByText("Running Execution"));
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByText("Skeleton")).toBeTruthy();
    loadingNextPage = false;
    rerender(<ExecutionPageContent />);
    expect(document.activeElement).toBe(
      screen.getByRole("button", { name: "View Other Execution execution details" }),
    );
  });

  it("focuses the list heading when changing the date leaves no results", () => {
    render(<ExecutionPageContent />);
    fireEvent.click(screen.getByText("Running Execution"));
    fireEvent.click(screen.getByRole("button", { name: "Change date" }));
    expect(screen.getByText("No executions found")).toBeTruthy();
    expect(document.activeElement).toBe(screen.getByRole("heading", { name: "Recent executions" }));
  });

  it("returns focus to the last viewed card after navigating forward then backward", () => {
    render(<ExecutionPageContent />);
    fireEvent.click(screen.getByText("Running Execution"));
    fireEvent.click(screen.getByRole("button", { name: "Next execution" }));
    fireEvent.click(screen.getByRole("button", { name: "Previous execution" }));
    fireEvent.keyDown(document, { key: "Escape" });
    expect(document.activeElement).toBe(
      screen.getByRole("button", { name: "View Running Execution execution details" }),
    );
  });

  it("does not close the panel for Escape handled by another dialog or during composition", () => {
    render(<ExecutionPageContent />);
    fireEvent.click(screen.getByText("Running Execution"));
    const panel = screen.getByRole("complementary", { name: "Execution details" });
    fireEvent.keyDown(document, { key: "Escape", isComposing: true });
    expect(panel.getAttribute("aria-hidden")).toBe("false");
    const dialog = document.createElement("div");
    dialog.setAttribute("role", "dialog");
    document.body.appendChild(dialog);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(panel.getAttribute("aria-hidden")).toBe("false");
    dialog.remove();
  });

  it("cancels the execution with its flow_run_id after confirming in the dialog", () => {
    render(<ExecutionPageContent />);

    openSidebarAndClickCancel();
    // Confirm inside the modal.
    fireEvent.click(screen.getByRole("button", { name: "Cancel Execution" }));

    expect(mockCancelMutate).toHaveBeenCalledTimes(1);
    expect(mockCancelMutate.mock.calls[0][0]).toEqual({ flowRunId: "flow-123" });
  });

  it("closes the dialog without cancelling when Close is clicked", () => {
    render(<ExecutionPageContent />);

    openSidebarAndClickCancel();
    fireEvent.click(screen.getByRole("button", { name: "Close" }));

    expect(
      screen.queryByText(
        "Are you sure you want to cancel this execution? This action cannot be undone.",
      ),
    ).toBeNull();
    expect(mockCancelMutate).not.toHaveBeenCalled();
  });

  it("shows a success toast when the cancellation request succeeds", () => {
    mockCancelMutate.mockImplementation((_vars, { onSuccess }) => onSuccess());
    render(<ExecutionPageContent />);

    openSidebarAndClickCancel();
    fireEvent.click(screen.getByRole("button", { name: "Cancel Execution" }));

    expect(mockToastSuccess).toHaveBeenCalledWith("Cancellation requested successfully");
    expect(mockToastError).not.toHaveBeenCalled();
  });

  it("invalidates the execution list and detail queries after a successful cancellation", () => {
    mockCancelMutate.mockImplementation((_vars, { onSuccess }) => onSuccess());
    render(<ExecutionPageContent />);

    openSidebarAndClickCancel();
    fireEvent.click(screen.getByRole("button", { name: "Cancel Execution" }));

    expect(mockInvalidateQueries).toHaveBeenCalledWith({ queryKey: ["/executions"] });
    expect(mockInvalidateQueries).toHaveBeenCalledWith({ queryKey: ["/executions/exec-1"] });
  });

  it("does not invalidate any query when the cancellation request fails", () => {
    mockCancelMutate.mockImplementation((_vars, { onError }) => onError({}));
    render(<ExecutionPageContent />);

    openSidebarAndClickCancel();
    fireEvent.click(screen.getByRole("button", { name: "Cancel Execution" }));

    expect(mockInvalidateQueries).not.toHaveBeenCalled();
  });

  it("shows an error toast with the server detail when cancellation fails", () => {
    mockCancelMutate.mockImplementation((_vars, { onError }) =>
      onError({ response: { data: { detail: "Execution already finished" } } }),
    );
    render(<ExecutionPageContent />);

    openSidebarAndClickCancel();
    fireEvent.click(screen.getByRole("button", { name: "Cancel Execution" }));

    expect(mockToastError).toHaveBeenCalledWith("Execution already finished");
    expect(mockToastSuccess).not.toHaveBeenCalled();
  });

  it("shows a fallback error toast when the server provides no detail", () => {
    mockCancelMutate.mockImplementation((_vars, { onError }) => onError({}));
    render(<ExecutionPageContent />);

    openSidebarAndClickCancel();
    fireEvent.click(screen.getByRole("button", { name: "Cancel Execution" }));

    expect(mockToastError).toHaveBeenCalledWith("Failed to cancel execution");
  });
});

describe("ExecutionPageContent failure investigation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    loadingNextPage = false;
  });

  afterEach(() => {
    cleanup();
    executionDetail = DEFAULT_DETAIL;
  });

  it("opens the investigation in the floating chat, not a second sidebar", () => {
    const log = `Traceback (most recent call last):\n${"/app/qdash/workflow/calibtasks/qubex/".repeat(20)}base.py`;
    executionDetail = { status: "failed", chip_id: "chip-1", message: log, task: [] };
    render(<ExecutionPageContent />);

    fireEvent.click(screen.getByText("Running Execution"));
    const panel = screen.getByRole("complementary", { name: "Execution details" });
    // The log sits in a scrolling block beside the action, not in a squeezed alert.
    const body = within(panel).getByText((_, element) => element?.textContent === log);
    expect(body.tagName).toBe("PRE");
    expect(body.className).toContain("overflow-auto");
    expect(within(panel).getByText("Error Log").parentElement).toContainElement(
      within(panel).getByRole("button", { name: "Investigate with AI" }),
    );

    fireEvent.click(within(panel).getByRole("button", { name: "Investigate with AI" }));

    expect(mockInvestigate).toHaveBeenCalledWith(
      { executionId: "exec-1", chipId: "chip-1" },
      "mini",
    );
    // The details panel stays open underneath the floating window.
    expect(panel.getAttribute("aria-hidden")).toBe("false");
  });

  it("still offers an investigation when the failure recorded no message", () => {
    executionDetail = { status: "failed", chip_id: "chip-1", message: "", task: [] };
    render(<ExecutionPageContent />);

    fireEvent.click(screen.getByText("Running Execution"));
    const panel = screen.getByRole("complementary", { name: "Execution details" });
    expect(within(panel).getByText("No error message recorded.")).toBeTruthy();
    fireEvent.click(within(panel).getByRole("button", { name: "Investigate with AI" }));

    expect(mockInvestigate).toHaveBeenCalledWith(
      { executionId: "exec-1", chipId: "chip-1" },
      "mini",
    );
  });
});

describe("ExecutionPageContent status presentation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    loadingNextPage = false;
  });

  afterEach(() => {
    cleanup();
    executionDetail = DEFAULT_DETAIL;
  });

  it("labels list statuses with text and a static icon instead of a pulse", () => {
    render(<ExecutionPageContent />);

    const runningCard = screen.getByRole("button", {
      name: "View Running Execution execution details",
    });
    const badge = within(runningCard).getByText("Running");
    expect(badge.className).toContain("badge-info");
    expect(badge.className).not.toContain("status-pulse");
    expect(badge.querySelector('svg[aria-hidden="true"]')).not.toBeNull();
    expect(document.querySelector(".status-pulse")).toBeNull();
  });

  it("renders task rows flat with text status cues and toggles their figures", () => {
    executionDetail = {
      ...DEFAULT_DETAIL,
      status: "running",
      task: [
        { name: "CheckRabi", qid: "0", status: "running", figure_path: ["a.png"] },
        { name: "CheckT1", qid: "1", status: "unexpected" },
      ],
    };
    render(<ExecutionPageContent />);
    fireEvent.click(screen.getByText("Running Execution"));
    const panel = screen.getByRole("complementary", { name: "Execution details" });

    const row = within(panel).getByText("0-CheckRabi").closest("h4")?.parentElement
      ?.parentElement as HTMLElement;
    const runningLabel = within(row).getByText("Running");
    expect(runningLabel.className).toContain("text-info");
    expect(runningLabel.className).not.toContain("status-pulse");
    expect(runningLabel.querySelector('svg[aria-hidden="true"]')).not.toBeNull();
    // Unknown task statuses keep reading as failed.
    const unknownRow = within(panel).getByText("1-CheckT1").closest("h4")?.parentElement
      ?.parentElement as HTMLElement;
    expect(within(unknownRow).getByText("Failed").className).toContain("text-error");
    expect(panel.querySelector(".status-pulse")).toBeNull();

    expect(row.className).not.toMatch(/shadow-(md|lg)/);
    expect(row.className).toContain("border-l-info");
    expect(within(panel).queryByText("TaskFigure")).toBeNull();

    fireEvent.click(row);
    expect(row.className).toContain("border-l-info");
    expect(within(panel).getByText("TaskFigure")).toBeTruthy();

    fireEvent.click(row);
    expect(within(panel).queryByText("TaskFigure")).toBeNull();
  });
});

type ListOptions = {
  query: { enabled?: boolean; queryKey?: unknown[] };
  request?: { headers: Record<string, string> };
};

function latestCall(mock: { mock: { calls: unknown[][] } }) {
  const calls = mock.mock.calls;
  return calls[calls.length - 1] as [ListArgs, ListOptions] | undefined;
}

const SESSION_ROW = {
  kind: "agent_session",
  sort_at: "2026-06-03T00:00:00Z",
  agent_session: {
    session_id: "session-1",
    project_id: "project-1",
    chip_id: "chip-1",
    created_by: "alice",
    created_at: "2026-06-02T00:00:00Z",
    updated_at: "2026-06-03T00:00:00Z",
    expires_at: "2026-06-04T00:00:00Z",
    status: "waiting_for_human",
    stored_status: "waiting_for_human",
    active_intervention_id: "int-1",
    qids: ["Q00"],
    allowed_tasks: ["CheckRabi"],
    autonomy: "auto",
    skill_name: "qdash-one-qubit-calibration",
    model_name: "",
    counts: {
      actions: 4,
      max_actions: 20,
      measurements: 2,
      pending_dispatch: 0,
      dispatch_failed: 0,
      in_flight: 0,
      rejected_proposals: 1,
      open_interventions: 1,
      decisions: 1,
    },
    latest_activity_at: "2026-06-03T00:00:00Z",
    missing: [],
  },
  children: [
    {
      action_id: "act-1",
      sequence: 1,
      attempt: 1,
      task_name: "CheckRabi",
      qid: "Q00",
      in_filter: true,
      execution: {
        execution_id: "agent-exec-1",
        name: "agent:CheckRabi-agent-exec-1",
        status: "completed",
        start_at: "2026-06-02T01:00:00Z",
        tags: [],
        note: {},
      },
    },
    {
      action_id: "act-2",
      sequence: 2,
      attempt: 2,
      task_name: "CheckRabi",
      qid: "Q00",
      in_filter: true,
      execution: {
        execution_id: "agent-exec-2",
        name: "agent:CheckRabi-agent-exec-2",
        status: "failed",
        start_at: "2026-06-03T00:00:00Z",
        tags: [],
        note: {},
      },
    },
  ],
  children_total: 2,
  children_in_filter: 2,
  children_omitted: 0,
};

const MANUAL_ROW = {
  kind: "execution",
  execution: {
    execution_id: "exec-1",
    name: "Running Execution",
    status: "running",
    start_at: "2026-06-01T00:00:00Z",
    tags: [],
    note: {},
  },
  children: [],
};

const CALIBRATION_ROW = {
  kind: "calibration_session",
  sort_at: "2026-06-05T00:00:00Z",
  calibration_session: {
    calibration_session_id: "cs-1",
    project_id: "project-1",
    chip_id: "chip-1",
    objective: "Shorten the 0-1 ZX90",
    status: "closed",
    created_by: "alice",
    created_at: "2026-06-04T00:00:00Z",
    closed_at: "2026-06-05T02:00:00Z",
    targets: ["0", "1", "0-1"],
    counts: {
      pipeline_runs: 2,
      agent_sessions: 1,
      executions: 3,
      executions_in_filter: 3,
      running: 0,
      failed: 1,
      unknown_dispatch: 0,
      decisions: 5,
    },
    first_activity_at: "2026-06-04T00:00:00Z",
    latest_activity_at: "2026-06-05T00:00:00Z",
    recommendation: null,
  },
  pipeline_runs: [
    {
      run_id: "cpr-1",
      pipeline_name: "zx90_q0_q1_c03",
      dispatch_status: "dispatched",
      requested_by: "alice",
      requested_at: "2026-06-04T01:00:00Z",
      decision_id: "cd-12345678",
      targets: ["0", "1"],
      executions: [
        {
          execution_id: "pipe-exec-1",
          name: "zx90_q0_q1_c03_step1",
          status: "failed",
          start_at: "2026-06-04T01:00:00Z",
          tags: [],
          note: {},
        },
      ],
      executions_total: 1,
      executions_in_filter: 1,
    },
    {
      run_id: "cpr-2",
      pipeline_name: "zx90_q0_q1_c04",
      dispatch_status: "rejected",
      requested_by: "alice",
      requested_at: "2026-06-04T02:00:00Z",
      decision_id: null,
      targets: [],
      executions: [],
      executions_total: 0,
      executions_in_filter: 0,
    },
  ],
  pipeline_runs_omitted: 0,
  nested_agent_sessions: [
    {
      agent_session: SESSION_ROW.agent_session,
      children: SESSION_ROW.children,
      children_total: 2,
      children_in_filter: 2,
      children_omitted: 0,
    },
  ],
  nested_agent_sessions_omitted: 0,
  children: [],
};

describe("ExecutionPageContent calibration session groups", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    loadingNextPage = false;
    executionDetail = DEFAULT_DETAIL;
    currentProjectId = "project-1";
    groupedError = false;
    groupedItems = [CALIBRATION_ROW, MANUAL_ROW];
    groupedSummary = {
      total: 2,
      total_executions: 4,
      grouped_executions: 3,
      agent_sessions: 0,
      calibration_sessions: 1,
    };
  });

  afterEach(() => {
    cleanup();
    groupedItems = null;
  });

  it("shows the objective, its records' counts, and links in the open project", () => {
    render(<ExecutionPageContent />);
    expect(screen.getByText("Shorten the 0-1 ZX90")).toBeTruthy();
    expect(
      screen.getByText("4 executions, 3 of them in 1 calibration session; 2 rows"),
    ).toBeTruthy();
    expect(
      screen.getByText(/2 pipeline runs · 1 agent session · 3 executions · 1 failed · 5 decisions/),
    ).toBeTruthy();
    expect(screen.getByText("Targets 0, 1, 0-1")).toBeTruthy();
    // Closed says nothing about the objective; no recommendation was recorded, so none is shown.
    expect(screen.getByText("Closed")).toBeTruthy();
    expect(screen.queryByText(/Recommends/)).toBeNull();
    expect(
      screen.getByRole("link", { name: "Open calibration session" }).getAttribute("href"),
    ).toBe("/calibration-sessions/cs-1?project=project-1");
    expect(screen.queryByText("zx90_q0_q1_c03_step1")).toBeNull();
  });

  it("expands to every run with its step executions and the nested agent session", () => {
    render(<ExecutionPageContent />);
    fireEvent.click(screen.getByRole("button", { expanded: false, name: /Shorten the 0-1 ZX90/ }));
    expect(screen.getByText("zx90_q0_q1_c03_step1")).toBeTruthy();
    expect(screen.getByText(/Carries out decision cd-12345/)).toBeTruthy();
    expect(screen.getByText("Refused before it started; nothing ran.")).toBeTruthy();
    // The nested agent session keeps its own row and does not repeat the parent link.
    expect(screen.getByText("qdash-one-qubit-calibration")).toBeTruthy();
    expect(screen.queryAllByRole("link", { name: /Calibration session:/ })).toHaveLength(0);
    fireEvent.click(screen.getByRole("button", { expanded: false, name: /qdash-one-qubit/ }));
    fireEvent.click(screen.getByText("zx90_q0_q1_c03_step1"));
    const panel = screen.getByRole("complementary", { name: "Execution details" });
    // Browsing covers the run's step, the agent session's two children, and the manual run.
    expect(within(panel).getByText("1 of 4 on this page")).toBeTruthy();
  });
});

describe("ExecutionPageContent agent session groups", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    loadingNextPage = false;
    executionDetail = DEFAULT_DETAIL;
    currentProjectId = "project-1";
    groupedError = false;
    groupedItems = [SESSION_ROW, MANUAL_ROW];
    groupedSummary = { total: 2, total_executions: 3, grouped_executions: 2, agent_sessions: 1 };
  });

  afterEach(() => {
    cleanup();
    groupedItems = null;
    executionDetail = DEFAULT_DETAIL;
  });

  it("shows a session as one row with its own status and explains the counts", () => {
    render(<ExecutionPageContent />);

    expect(screen.getByText("qdash-one-qubit-calibration")).toBeTruthy();
    // The group status is the session's, not a failure of its last execution.
    expect(screen.getByText("Paused for an expert")).toBeTruthy();
    expect(screen.getByText(/Waiting for an expert/)).toBeTruthy();
    expect(screen.getByText("3 executions, 2 of them in 1 agent session; 2 rows")).toBeTruthy();
    expect(screen.getByText(/1 rejected proposal/)).toBeTruthy();
    expect(screen.getByRole("link", { name: "Open session graph" }).getAttribute("href")).toBe(
      "/execution/chip-1/sessions/session-1?project=project-1",
    );
    // Children stay folded until the row is expanded.
    expect(screen.queryByText("agent:CheckRabi-agent-exec-1")).toBeNull();
    const lastCall = latestCall(mockListGroups);
    expect(lastCall?.[1].query.enabled).toBe(true);
    expect(latestCall(mockListExecutions)?.[1].query.enabled).toBe(false);
  });

  it("expands a session and opens a child in the existing details panel", () => {
    render(<ExecutionPageContent />);
    const toggle = screen.getByRole("button", { expanded: false, name: /qdash-one-qubit/ });
    fireEvent.click(toggle);
    expect(toggle.getAttribute("aria-expanded")).toBe("true");
    expect(screen.getByText("agent:CheckRabi-agent-exec-1")).toBeTruthy();
    expect(screen.getByText("#2 · try 2")).toBeTruthy();

    fireEvent.click(screen.getByText("agent:CheckRabi-agent-exec-2"));
    const panel = screen.getByRole("complementary", { name: "Execution details" });
    expect(panel.getAttribute("aria-hidden")).toBe("false");
    // Browsing covers the visible executions: both children and the manual run.
    expect(within(panel).getByText("2 of 3 on this page")).toBeTruthy();

    fireEvent.click(toggle);
    expect(screen.queryByText("agent:CheckRabi-agent-exec-1")).toBeNull();
  });

  it("links the details panel to the execution's agent session", () => {
    executionDetail = {
      ...DEFAULT_DETAIL,
      chip_id: "chip-1",
      agent_session: {
        session_id: "session-1",
        linked: true,
        action_id: "act-1",
        status: "active",
      },
    };
    render(<ExecutionPageContent />);
    fireEvent.click(screen.getByText("Running Execution"));
    const panel = screen.getByRole("complementary", { name: "Execution details" });
    expect(within(panel).getByText(/One measurement of agent session/)).toBeTruthy();
    expect(
      within(panel).getByRole("link", { name: "Open session graph" }).getAttribute("href"),
    ).toBe("/execution/chip-1/sessions/session-1");
  });

  it("switches to the flat list without grouping", () => {
    render(<ExecutionPageContent />);
    fireEvent.click(screen.getByRole("checkbox", { name: "Group sessions" }));

    expect(latestCall(mockListExecutions)?.[1].query.enabled).toBe(true);
    expect(latestCall(mockListGroups)?.[1].query.enabled).toBe(false);
    expect(screen.queryByText("qdash-one-qubit-calibration")).toBeNull();
    expect(screen.getByText("40 executions")).toBeTruthy();
    expect(screen.getByText("Completed Execution")).toBeTruthy();
  });

  it("resets expanded groups and the panel when the project changes", () => {
    const { rerender } = render(<ExecutionPageContent />);
    fireEvent.click(screen.getByRole("button", { expanded: false, name: /qdash-one-qubit/ }));
    fireEvent.click(screen.getByText("agent:CheckRabi-agent-exec-1"));
    expect(
      screen.getByRole("complementary", { name: "Execution details" }).getAttribute("aria-hidden"),
    ).toBe("false");

    currentProjectId = "project-2";
    rerender(<ExecutionPageContent />);

    expect(document.getElementById("execution-details-panel")?.getAttribute("aria-hidden")).toBe(
      "true",
    );
    expect(screen.queryByText("agent:CheckRabi-agent-exec-1")).toBeNull();
    // The grouped request is pinned to the new project.
    const options = latestCall(mockListGroups)?.[1];
    expect(options?.query.queryKey).toContain("project-2");
    expect(options?.request?.headers["X-Project-Id"]).toBe("project-2");
  });

  it("gives a session card the accent of an execution card in the same state", () => {
    const sessionCard = (status: string) => {
      groupedItems = [
        { ...SESSION_ROW, agent_session: { ...SESSION_ROW.agent_session, status } },
        MANUAL_ROW,
      ];
      const view = render(<ExecutionPageContent />);
      const card = screen.getByTestId("agent-session-card");
      const className = card.className;
      view.unmount();
      return className;
    };

    // The manual row is a running execution card.
    render(<ExecutionPageContent />);
    const runningCard = screen.getByRole("button", {
      name: "View Running Execution execution details",
    });
    expect(runningCard.className).toContain("border-l-info");
    cleanup();

    const active = sessionCard("active");
    expect(active).toContain("border-l-4");
    expect(active).toContain("border-l-info");
    expect(sessionCard("completed")).toContain("border-l-success");
    expect(sessionCard("cancelled")).toContain("border-l-neutral");
    expect(sessionCard("waiting_for_human")).toContain("border-l-warning");
    const expired = sessionCard("expired");
    expect(expired).toContain("border-l-base-300");
    expect(expired).not.toMatch(/border-l-(info|success|warning|error|neutral)/);
  });

  it("reports a grouped list that cannot be loaded", () => {
    groupedError = true;
    render(<ExecutionPageContent />);
    expect(screen.getByRole("alert").textContent).toContain(
      "Execution history could not be loaded",
    );
  });
});

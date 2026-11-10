import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { HomePageContent } from "@/components/features/home/HomePageContent";
import { journeyStorageKey } from "@/lib/firstCalibrationJourney";

const mockExecutionActivity = vi.hoisted(() => vi.fn());
const mockExecution = vi.hoisted(() => vi.fn());
const mockChips = vi.hoisted(() => vi.fn());
const mockTaskResults = vi.hoisted(() => vi.fn());
const mockSchedules = vi.hoisted(() => vi.fn());
const mockConfigSources = vi.hoisted(() => vi.fn());
const mockFlow = vi.hoisted(() => vi.fn());
const mockPush = vi.hoisted(() => vi.fn());
const mockProject = vi.hoisted(() => vi.fn());

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush, replace: vi.fn() }),
  usePathname: () => "/home",
}));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ username: "alice" }),
}));

// Only the activity hook and the journey's execution lookup are provided: the page must not poll
// the lock or a running execution, since the global execution indicator already shows progress.
vi.mock("@/client/execution/execution", async (importOriginal) => ({
  getGetExecutionQueryKey: (await importOriginal<typeof import("@/client/execution/execution")>())
    .getGetExecutionQueryKey,
  getGetExecutionActivityQueryKey: () => ["/executions/activity"],
  useGetExecutionActivity: mockExecutionActivity,
  useGetExecution: mockExecution,
}));

vi.mock("@/contexts/ThemeContext", () => ({ useIsDarkTheme: () => false }));

function day(date: string, counts: Partial<Record<string, number>> = {}) {
  const merged = { completed: 0, failed: 0, running: 0, scheduled: 0, cancelled: 0, other: 0 };
  Object.assign(merged, counts);
  return { date, ...merged, total: Object.values(merged).reduce((a, b) => a + b, 0) };
}

vi.mock("@/client/chip/chip", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  useListChips: mockChips,
  useListChipConfigSources: mockConfigSources,
}));

vi.mock("@/client/task-result/task-result", () => ({
  useListTaskResults: mockTaskResults,
}));

vi.mock("@/client/flow/flow", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  useGetFlow: mockFlow,
  useListAllFlowSchedules: mockSchedules,
}));

vi.mock("@/contexts/ProjectContext", () => ({
  useProject: mockProject,
}));

const FAKE_SOURCES = {
  data: {
    data: {
      available: true,
      sources: [],
      deployment_backend: "fake",
      presets: [
        {
          preset_id: "fake",
          name: "Virtual fake device",
          description: "",
          topology_id: "square-lattice-mux-64",
          n_qubits: 64,
          mux_count: 16,
          workflow_template_id: "fake_calibration",
        },
      ],
    },
  },
  isError: false,
};

const KEY = journeyStorageKey("alice", "project-1");

function storeJourney(overrides: Record<string, unknown>, key = KEY) {
  window.localStorage.setItem(
    key,
    JSON.stringify({
      version: 1,
      status: "active",
      chipId: null,
      flowName: null,
      executionId: null,
      hardwareConfirmedChipId: null,
      inspectedTaskId: null,
      chipOverviewSeen: false,
      startedAt: "2026-11-05T00:00:00.000Z",
      updatedAt: "2026-11-05T00:00:00.000Z",
      ...overrides,
    }),
  );
}

function storedJourney() {
  const raw = window.localStorage.getItem(KEY);
  return raw ? JSON.parse(raw) : null;
}

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
    mockConfigSources.mockReturnValue(FAKE_SOURCES);
    mockFlow.mockReturnValue({ data: undefined, isLoading: false, isError: false, error: null });
    mockExecution.mockReturnValue({ data: undefined });
    mockSchedules.mockReturnValue({
      data: { data: { schedules: [] } },
      isLoading: false,
      error: null,
    });
    mockChips.mockReturnValue({
      data: { data: { chips: [{ chip_id: "chip-1", size: 64 }] } },
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
    window.localStorage.clear();
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
    // A project with chips keeps the guide one click away instead of a card.
    expect(screen.getByRole("button", { name: "First calibration guide" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "First calibration" })).toBeNull();
    expect(screen.queryByRole("link", { name: "Setup tour" })).toBeNull();
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

    expect(screen.getByText("No executions in the last 90 days")).toBeTruthy();
    expect(screen.getByText("No failed task results")).toBeTruthy();
  });

  it("starts the first calibration at chip creation when the project has no chips", () => {
    mockChips.mockReturnValue({
      data: { data: { chips: [] } },
      isLoading: false,
      error: null,
    });

    render(<HomePageContent />);

    expect(screen.getByRole("heading", { name: "First calibration" })).toBeTruthy();
    expect(screen.getByText(/64-qubit virtual device/)).toBeTruthy();
    expect(screen.getAllByRole("listitem").map((item) => item.textContent)).toEqual(
      expect.arrayContaining([expect.stringContaining("Prepare a chip")]),
    );
    fireEvent.click(screen.getByRole("button", { name: "Create a chip" }));

    expect(storedJourney()).toMatchObject({ status: "active", chipId: null });
    expect(mockPush).toHaveBeenCalledWith("/chip?journey=create-chip");
  });

  it("starts with an existing chip of the virtual device instead of creating a duplicate", () => {
    mockChips.mockReturnValue({
      data: {
        data: {
          chips: [
            { chip_id: "small-chip", size: 16, installed_at: "2026-11-04T00:00:00Z" },
            { chip_id: "fake64", size: 64, installed_at: "2026-11-01T00:00:00Z" },
          ],
        },
      },
      isLoading: false,
      error: null,
    });

    render(<HomePageContent />);
    fireEvent.click(screen.getByRole("button", { name: "First calibration guide" }));

    const select = screen.getByLabelText("Chip to calibrate") as HTMLSelectElement;
    // The fake backend calibrates 64 qubits, so the 16-qubit chip is not offered.
    expect(Array.from(select.options).map((option) => option.value)).toEqual(["fake64", ""]);
    expect(select.value).toBe("fake64");
    fireEvent.click(screen.getByRole("button", { name: "Start" }));

    expect(storedJourney()).toMatchObject({ status: "active", chipId: "fake64" });
    expect(mockPush).toHaveBeenCalledWith(
      "/workflow/new?backend=fake&template=fake_calibration&chip_id=fake64&journey=first-calibration",
    );
  });

  it("creates a new chip when that is chosen although the project has chips", () => {
    mockChips.mockReturnValue({
      data: {
        data: {
          chips: [{ chip_id: "fake64", size: 64, installed_at: "2026-11-01T00:00:00Z" }],
        },
      },
      isLoading: false,
      error: null,
    });

    render(<HomePageContent />);
    fireEvent.click(screen.getByRole("button", { name: "First calibration guide" }));
    const select = screen.getByLabelText("Chip to calibrate") as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "" } });
    expect(select.value).toBe("");
    fireEvent.click(screen.getByRole("button", { name: "Start" }));

    expect(storedJourney()).toMatchObject({ status: "active", chipId: null });
    expect(mockPush).toHaveBeenCalledWith("/chip?journey=create-chip");
  });

  it("resumes a paused journey at the stage the server confirms", () => {
    storeJourney({ status: "paused", chipId: "chip-1", flowName: "first_calibration" });
    mockFlow.mockReturnValue({
      data: { data: { name: "first_calibration", chip_id: "chip-1" } },
      isLoading: false,
      isError: false,
      error: null,
    });

    render(<HomePageContent />);

    expect(screen.getByText("Paused")).toBeTruthy();
    expect(screen.getByText("Review and run").closest("li")).toHaveAttribute(
      "aria-current",
      "step",
    );
    fireEvent.click(screen.getByRole("button", { name: "Resume: Open the flow to run it" }));

    expect(storedJourney()).toMatchObject({ status: "active", flowName: "first_calibration" });
    expect(mockPush).toHaveBeenCalledWith("/workflow/first_calibration");
  });

  it("offers recovery when the journey's chip was deleted", () => {
    storeJourney({ chipId: "deleted-chip" });

    render(<HomePageContent />);

    expect(screen.getByText(/Chip deleted-chip no longer exists/)).toBeTruthy();
    expect(screen.getByText("Prepare a chip").closest("li")).toHaveAttribute(
      "aria-current",
      "step",
    );
    // The project's other chip can be picked instead of creating one.
    expect((screen.getByLabelText("Chip to calibrate") as HTMLSelectElement).value).toBe("chip-1");
  });

  it("never shows a journey stored for another project or user", () => {
    storeJourney({ chipId: "chip-1" }, journeyStorageKey("alice", "project-2"));
    storeJourney({ chipId: "chip-1" }, journeyStorageKey("bob", "project-1"));

    render(<HomePageContent />);

    expect(screen.queryByRole("heading", { name: "First calibration" })).toBeNull();
    expect(screen.getByRole("button", { name: "First calibration guide" })).toBeTruthy();
  });

  it("hides the guide from viewers even when a journey is stored", () => {
    mockProject.mockReturnValue({ canEdit: false, projectId: "project-1" });
    storeJourney({ chipId: "chip-1" });

    render(<HomePageContent />);

    expect(screen.queryByRole("heading", { name: "First calibration" })).toBeNull();
    expect(screen.queryByRole("button", { name: "First calibration guide" })).toBeNull();
  });

  it("replaces the current execution card with project-wide activity", () => {
    render(<HomePageContent />);

    expect(mockExecutionActivity).toHaveBeenCalled();
    const [params] = mockExecutionActivity.mock.calls[0];
    expect(params).toEqual({ days: 90, timezone: expect.any(String) });
    expect(params).not.toHaveProperty("chip_id");
    expect(screen.queryByRole("heading", { name: "Current execution" })).toBeNull();
    expect(screen.queryByText(/tasks$/)).toBeNull();
    expect(screen.getByRole("link", { name: /All executions/ }).getAttribute("href")).toBe(
      "/execution",
    );
    expect(screen.getByRole("heading", { name: "Needs attention" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "Recent notifications" })).toBeNull();
  });

  describe("first calibration start", () => {
    const noChips = { data: { data: { chips: [] } }, isLoading: false, error: null };

    it("shows that the deployment is being checked and offers no start yet", () => {
      mockChips.mockReturnValue(noChips);
      mockConfigSources.mockReturnValue({ data: undefined, isError: false });

      render(<HomePageContent />);

      const card = screen.getByRole("heading", { name: "First calibration" }).closest("section");
      expect(card).toHaveAttribute("aria-busy", "true");
      expect(screen.getByRole("status").textContent).toContain("Checking this deployment");
      expect(screen.queryByRole("button", { name: "Create a chip" })).toBeNull();
      expect(mockPush).not.toHaveBeenCalled();
    });

    it("explains a failed check and retries it", () => {
      const refetchConfig = vi.fn();
      const refetchChips = vi.fn();
      mockChips.mockReturnValue({ ...noChips, refetch: refetchChips });
      mockConfigSources.mockReturnValue({ data: undefined, isError: true, refetch: refetchConfig });

      render(<HomePageContent />);

      expect(screen.getByRole("alert").textContent).toContain(
        "could not check how this deployment runs calibrations",
      );
      expect(screen.queryByRole("button", { name: "Create a chip" })).toBeNull();
      expect(screen.queryByLabelText("Chip to calibrate")).toBeNull();
      fireEvent.click(screen.getByRole("button", { name: "Try again" }));
      expect(refetchConfig).toHaveBeenCalled();
      expect(refetchChips).toHaveBeenCalled();
      expect(storedJourney()).toBeNull();
    });

    it("does not fall back to hardware when a fake deployment offers no virtual device", () => {
      mockConfigSources.mockReturnValue({
        data: { data: { available: true, sources: [], deployment_backend: "fake", presets: [] } },
        isError: false,
      });

      render(<HomePageContent />);
      fireEvent.click(screen.getByRole("button", { name: "First calibration guide" }));

      expect(screen.getByRole("alert").textContent).toContain("does not offer its virtual device");
      expect(screen.queryByLabelText("Chip to calibrate")).toBeNull();
      expect(screen.queryByRole("button", { name: "Start" })).toBeNull();
    });

    it("offers no chip creation when the fake device's configuration is not mounted", () => {
      mockConfigSources.mockReturnValue({
        ...FAKE_SOURCES,
        data: { data: { ...FAKE_SOURCES.data.data, available: false } },
      });
      mockChips.mockReturnValue({
        data: { data: { chips: [{ chip_id: "fake64", size: 64 }] } },
        isLoading: false,
        error: null,
      });

      render(<HomePageContent />);
      fireEvent.click(screen.getByRole("button", { name: "First calibration guide" }));

      const select = screen.getByLabelText("Chip to calibrate") as HTMLSelectElement;
      expect(Array.from(select.options).map((option) => option.value)).toEqual(["fake64"]);
    });

    it("asks for hardware readiness on Home before it links to the editor", () => {
      mockConfigSources.mockReturnValue({
        data: {
          data: {
            available: true,
            sources: [{ system_id: "chip-1", backend: "qubex", mux_count: 16, files: [] }],
            deployment_backend: "qubex",
            presets: [],
          },
        },
        isError: false,
      });

      render(<HomePageContent />);
      fireEvent.click(screen.getByRole("button", { name: "First calibration guide" }));
      fireEvent.click(screen.getByRole("button", { name: "Start" }));

      // The chip is chosen, but nothing opens until the user confirms the hardware.
      expect(storedJourney()).toMatchObject({ status: "active", chipId: "chip-1" });
      expect(mockPush).not.toHaveBeenCalled();
      const readiness = screen.getByRole("group", { name: "Hardware readiness of chip-1" });
      expect(document.activeElement).toBe(readiness);
      expect(screen.getByText(/before you prepare the calibration/)).toBeTruthy();
      expect(screen.queryByRole("button", { name: /Review the calibration/ })).toBeNull();

      fireEvent.click(screen.getByRole("checkbox"));
      fireEvent.click(screen.getByRole("button", { name: "Review the calibration" }));

      expect(storedJourney().hardwareConfirmedChipId).toBe("chip-1");
      expect(mockPush).toHaveBeenCalledWith(
        "/workflow/new?chip_id=chip-1&journey=first-calibration",
      );
    });
  });
});

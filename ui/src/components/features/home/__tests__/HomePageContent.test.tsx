import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { HomePageContent } from "@/components/features/home/HomePageContent";
import { journeyStorageKey } from "@/lib/firstCalibrationJourney";

const mockExecutionLock = vi.hoisted(() => vi.fn());
const mockExecution = vi.hoisted(() => vi.fn());
const mockChips = vi.hoisted(() => vi.fn());
const mockTaskResults = vi.hoisted(() => vi.fn());
const mockNotifications = vi.hoisted(() => vi.fn());
const mockConfigSources = vi.hoisted(() => vi.fn());
const mockFlow = vi.hoisted(() => vi.fn());
const mockPush = vi.hoisted(() => vi.fn());
const mockProject = vi.hoisted(() => ({ canEdit: true, projectId: "project-1" }));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mockPush, replace: vi.fn() }),
  usePathname: () => "/home",
}));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ username: "alice" }),
}));

vi.mock("@/client/flow/flow", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  useGetFlow: mockFlow,
}));

vi.mock("@/client/execution/execution", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  useGetExecutionLockStatus: mockExecutionLock,
  useGetExecution: mockExecution,
}));

vi.mock("@/client/chip/chip", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  useListChips: mockChips,
  useListChipConfigSources: mockConfigSources,
}));

vi.mock("@/client/task-result/task-result", () => ({
  useListTaskResults: mockTaskResults,
}));

vi.mock("@/contexts/ProjectContext", () => ({
  useProject: () => mockProject,
}));

vi.mock("@/hooks/useNotifications", () => ({
  useNotifications: mockNotifications,
  useNotificationActions: () => ({ markRead: { mutate: vi.fn() } }),
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

describe("HomePageContent", () => {
  beforeEach(() => {
    mockProject.canEdit = true;
    mockProject.projectId = "project-1";
    mockConfigSources.mockReturnValue(FAKE_SOURCES);
    mockFlow.mockReturnValue({ data: undefined, isLoading: false, isError: false, error: null });
    mockChips.mockReturnValue({
      data: { data: { chips: [{ chip_id: "chip-1", size: 64 }] } },
      isLoading: false,
      error: null,
    });
    mockExecution.mockReturnValue({ data: undefined });
    mockExecutionLock.mockReturnValue({
      data: {
        data: {
          lock: true,
          execution_id: "execution-1",
          chip_id: "chip-1",
          name: "Daily calibration",
          status: "running",
        },
      },
      isLoading: false,
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
    mockNotifications.mockReturnValue({
      data: {
        data: {
          notifications: [
            {
              id: "notification-1",
              kind: "forum_reply",
              title: "A new reply",
              excerpt: "Please review this result",
              actor_username: "alice",
              created_at: new Date().toISOString(),
              target_url: "/forum/post-1",
              read_at: null,
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
  });

  it("summarizes active work and items that need attention", () => {
    render(<HomePageContent />);

    expect(screen.getByRole("heading", { name: "Home" })).toBeTruthy();
    expect(screen.getByText("Daily calibration")).toBeTruthy();
    expect(screen.getByText("CheckRabi")).toBeTruthy();
    expect(screen.getByText("A new reply")).toBeTruthy();
    expect(screen.getByRole("link", { name: /Run a task/ }).getAttribute("href")).toBe("/tasks");
    expect(screen.getByRole("link", { name: /View inbox/ }).getAttribute("href")).toBe("/inbox");
    // A project with chips keeps the guide one click away instead of a card.
    expect(screen.getByRole("button", { name: "First calibration guide" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "First calibration" })).toBeNull();
  });

  it("keeps the home grids single column until the layout breakpoints", () => {
    const { container } = render(<HomePageContent />);

    const quickActions = container.querySelector("[aria-labelledby='quick-actions-heading'] > div");
    expect(quickActions?.className).toContain("grid-cols-1");

    const overview = container.querySelector('[class*="xl:grid-cols-[minmax(0,1.15fr)"]');
    expect(overview?.className).toContain("grid-cols-1");
  });

  it("shows calm empty states when no work is waiting", () => {
    mockExecutionLock.mockReturnValue({
      data: { data: { lock: false } },
      isLoading: false,
    });
    mockTaskResults.mockReturnValue({
      data: { data: { items: [] } },
      isLoading: false,
      error: null,
    });
    mockNotifications.mockReturnValue({
      data: { data: { notifications: [] } },
      isLoading: false,
      error: null,
    });

    render(<HomePageContent />);

    expect(screen.getByText("No calibration is running")).toBeTruthy();
    expect(screen.getByText("No failed task results")).toBeTruthy();
    expect(screen.getByText("You are all caught up")).toBeTruthy();
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
    mockProject.canEdit = false;
    storeJourney({ chipId: "chip-1" });

    render(<HomePageContent />);

    expect(screen.queryByRole("heading", { name: "First calibration" })).toBeNull();
    expect(screen.queryByRole("button", { name: "First calibration guide" })).toBeNull();
  });

  it("shows task progress for the running execution", () => {
    mockExecution.mockReturnValue({
      data: {
        data: {
          task: [
            { name: "CheckT1", status: "completed" },
            { name: "CheckT2Echo", status: "completed" },
            { name: "CheckRamsey", status: "running" },
            { name: "RandomizedBenchmarking", status: "scheduled" },
          ],
        },
      },
    });

    render(<HomePageContent />);

    expect(screen.getByText(/2\/4 tasks/)).toBeTruthy();
    expect(screen.getByText("CheckRamsey")).toBeTruthy();
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

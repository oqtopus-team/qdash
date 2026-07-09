import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { DashboardPageContent } from "@/components/features/dashboard/DashboardPageContent";

const mockSetSelectedChip = vi.fn();
const mockSetSelectionMode = vi.fn();
const mockSetStartDate = vi.fn();
const mockSetEndDate = vi.fn();
const mockSetQuickRange = vi.fn();
const mockForumPosts = vi.hoisted(() => vi.fn<() => unknown[]>(() => []));
const mockCurrentCooldownId = vi.hoisted(() => vi.fn<() => string | null>(() => null));
const mockCooldowns = vi.hoisted(() => vi.fn<() => unknown[]>(() => []));
const mockListForumPosts = vi.hoisted(() => vi.fn());

vi.mock("@/client/chip/chip", () => ({
  useListChips: () => ({
    data: {
      data: {
        chips: [{ chip_id: "chip-1", installed_at: "2026-06-01T00:00:00Z" }],
      },
    },
    isLoading: false,
  }),
  useGetChip: () => ({
    data: {
      data: {
        chip_id: "chip-1",
        size: 1,
        topology_id: "test-topology",
        current_cooldown_id: mockCurrentCooldownId(),
        note: null,
      },
    },
  }),
}));

vi.mock("@/client/cooldown/cooldown", () => ({
  useListCooldowns: () => ({
    data: { data: { cooldowns: mockCooldowns() } },
  }),
}));

vi.mock("@/client/forum/forum", () => ({
  useListForumPosts: (params: unknown, options: unknown) => {
    mockListForumPosts(params, options);
    return {
      data: { data: { posts: mockForumPosts(), total: 0, skip: 0, limit: 200 } },
    };
  },
}));

vi.mock("@/client/metrics/metrics", () => ({
  useGetChipMetrics: () => ({
    data: {
      data: {
        qubit_metrics: {
          t1: {
            Q0: { value: null, stddev: null },
          },
        },
        coupling_metrics: {
          zx90_gate_fidelity: {
            "0-1": { value: null, stddev: null },
          },
        },
      },
    },
    isLoading: false,
    isError: false,
  }),
}));

vi.mock("@/client/note/note", () => ({
  useGetChipNotesSummary: () => ({
    data: {
      data: {
        qubits: [],
        couplings: [],
        task_notes: [],
      },
    },
  }),
}));

vi.mock("@/client/projects/projects", () => ({
  useListProjectMembers: () => ({
    data: {
      data: {
        members: [],
      },
    },
  }),
}));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({
    user: { username: "tester" },
  }),
}));

vi.mock("@/contexts/ProjectContext", () => ({
  useProject: () => ({
    projectId: "project-1",
  }),
}));

vi.mock("@/hooks/useMetricsConfig", () => ({
  useMetricsConfig: () => ({
    qubitMetrics: [{ key: "t1", title: "T1", unit: "us", scale: 1 }],
    couplingMetrics: [
      { key: "zx90_gate_fidelity", title: "ZX90 Gate Fidelity", unit: "", scale: 1 },
    ],
    colorScale: { colors: ["#111111", "#222222"] },
    isLoading: false,
    isError: false,
  }),
}));

vi.mock("@/hooks/useMetricsQueryParams", () => ({
  useMetricsQueryParams: () => ({
    queryParams: {
      selection_mode: "latest",
      start_at: "2026-06-01T00:00:00Z",
      end_at: "2026-06-08T00:00:00Z",
    },
    canFetch: true,
  }),
}));

vi.mock("@/hooks/useUrlState", () => ({
  useMetricsUrlState: () => ({
    selectedChip: "chip-1",
    selectionMode: "latest",
    setSelectedChip: mockSetSelectedChip,
    setSelectionMode: mockSetSelectionMode,
  }),
  useRangeModeUrlState: () => ({
    startDate: "2026-06-01T00:00",
    endDate: "2026-06-08T00:00",
    setStartDate: mockSetStartDate,
    setEndDate: mockSetEndDate,
    setQuickRange: mockSetQuickRange,
  }),
}));

vi.mock("@/components/selectors/ChipSelector", () => ({
  ChipSelector: () => <div>ChipSelector</div>,
}));

vi.mock("@/components/selectors/CooldownSelector", () => ({
  CooldownSelector: () => <div>CooldownSelector</div>,
}));

vi.mock("@/components/ui/Card", () => ({
  Card: ({ children, title }: { children: React.ReactNode; title?: string }) => (
    <section>
      {title && <h2>{title}</h2>}
      {children}
    </section>
  ),
}));

vi.mock("@/components/ui/EmptyState", () => ({
  EmptyState: ({ title }: { title: string }) => <div>{title}</div>,
}));

vi.mock("@/components/ui/LinearGauge", () => ({
  LinearGauge: () => <div>LinearGauge</div>,
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

vi.mock("@/components/ui/QuantumLoader", () => ({
  QuantumLoader: () => <div>Loading...</div>,
}));

vi.mock("@/components/ui/TimeRangeSelector", () => ({
  TimeRangeSelector: () => <div>TimeRangeSelector</div>,
}));

vi.mock("@/components/ui/Skeleton/PageSkeletons", () => ({
  MetricsPageSkeleton: () => <div>Skeleton</div>,
}));

vi.mock("@/components/features/dashboard/DashboardCdfChart", () => ({
  DashboardCdfChart: () => <div>CdfChart</div>,
}));

vi.mock("@/components/features/dashboard/DashboardSummaryTable", () => ({
  DashboardSummaryTable: () => <div>SummaryTable</div>,
}));

vi.mock("@/components/features/dashboard/DashboardChipNoteCard", () => ({
  DashboardChipNoteCard: () => <div data-testid="chip-note-card" />,
}));

vi.mock("@/components/features/dashboard/DashboardTargetNoteModal", () => ({
  DashboardTargetNoteModal: ({ targetId }: { targetId: string }) => (
    <div data-testid="target-note-modal">{targetId}</div>
  ),
}));

vi.mock("@/components/features/dashboard/DashboardMetricModal", () => ({
  DashboardMetricModal: ({ targetId, metricKey }: { targetId: string; metricKey: string }) => (
    <div data-testid="metric-note-modal">{`${targetId}:${metricKey}`}</div>
  ),
}));

vi.mock("@/components/features/dashboard/DashboardQubitGrid", () => ({
  DashboardQubitGrid: ({
    forumLinkedQids,
    onQubitClick,
  }: {
    forumLinkedQids?: Record<string, string>;
    onQubitClick?: (qid: string) => void;
  }) => (
    <div>
      <span data-testid="qubit-forum-label">{forumLinkedQids?.["0"] ?? "none"}</span>
      <button type="button" onClick={() => onQubitClick?.("0")}>
        Open qubit
      </button>
    </div>
  ),
}));

vi.mock("@/components/features/dashboard/DashboardCouplingGrid", () => ({
  DashboardCouplingGrid: ({
    forumLinkedTargets,
    onCouplingClick,
  }: {
    forumLinkedTargets?: Record<string, string>;
    onCouplingClick?: (couplingId: string) => void;
  }) => (
    <div>
      <span data-testid="coupling-forum-label">{forumLinkedTargets?.["0-1"] ?? "none"}</span>
      <button type="button" onClick={() => onCouplingClick?.("0-1")}>
        Open coupling
      </button>
    </div>
  ),
}));

describe("DashboardPageContent", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockForumPosts.mockReturnValue([]);
    mockCurrentCooldownId.mockReturnValue(null);
    mockCooldowns.mockReturnValue([]);
  });

  afterEach(() => {
    cleanup();
  });

  it("filters dashboard forum markers by the active cool-down", async () => {
    mockCurrentCooldownId.mockReturnValue("cd-active");
    mockCooldowns.mockReturnValue([
      {
        cooldown_id: "cd-active",
        started_at: "2026-06-01T00:00:00Z",
        ended_at: null,
      },
    ]);

    render(<DashboardPageContent />);

    await waitFor(() => {
      expect(mockListForumPosts).toHaveBeenLastCalledWith(
        expect.objectContaining({
          chip_id: "chip-1",
          cooldown_id: "cd-active",
          status: null,
          limit: 200,
        }),
        expect.anything(),
      );
    });
  });

  it("maps forum labels to dashboard marker labels", () => {
    mockForumPosts.mockReturnValue([
      {
        id: "forum-0",
        target_type: "qubit",
        target_id: "0",
        labels: ["anomaly"],
      },
      {
        id: "forum-1",
        target_type: "qubit",
        target_id: "0",
        labels: ["review"],
      },
      {
        id: "forum-2",
        target_type: "coupling",
        target_id: "0-1",
        labels: ["anomaly"],
      },
    ]);

    render(<DashboardPageContent />);

    expect(screen.getAllByTestId("qubit-forum-label").map((item) => item.textContent)).toContain(
      "anomaly",
    );
    expect(screen.getAllByTestId("coupling-forum-label").map((item) => item.textContent)).toContain(
      "anomaly",
    );
  });

  it("opens the pinned summary modal from the empty qubit topology", () => {
    render(<DashboardPageContent />);

    fireEvent.click(screen.getAllByRole("button", { name: "Open qubit" })[0]);

    expect(screen.getByTestId("target-note-modal").textContent).toContain("0");
    expect(screen.queryByTestId("metric-note-modal")).toBeNull();
  });

  it("opens the pinned summary modal from the empty coupling topology", () => {
    render(<DashboardPageContent />);

    fireEvent.click(screen.getAllByRole("button", { name: "Open coupling" })[0]);

    expect(screen.getByTestId("target-note-modal").textContent).toContain("0-1");
    expect(screen.queryByTestId("metric-note-modal")).toBeNull();
  });

  it("opens the metric history modal for a qubit metric even when the metric value is missing", () => {
    render(<DashboardPageContent />);

    fireEvent.click(screen.getAllByRole("button", { name: "Open qubit" })[1]);

    expect(screen.getByTestId("metric-note-modal").textContent).toContain("0:t1");
    expect(screen.queryByTestId("target-note-modal")).toBeNull();
  });

  it("opens the metric history modal for a coupling metric even when the metric value is missing", () => {
    render(<DashboardPageContent />);

    const couplingButtons = screen.getAllByRole("button", { name: "Open coupling" });
    fireEvent.click(couplingButtons[couplingButtons.length - 1]);

    expect(screen.getByTestId("metric-note-modal").textContent).toContain("0-1:zx90_gate_fidelity");
    expect(screen.queryByTestId("target-note-modal")).toBeNull();
  });
});

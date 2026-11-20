import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { CustomDashboardResponse, DashboardPanelResponse } from "@/schemas";

import { CustomDashboardPageContent } from "../CustomDashboardPageContent";

const mocks = vi.hoisted(() => ({
  canEdit: true,
  dashboard: null as unknown,
  error: null as unknown,
  update: vi.fn(),
  evaluate: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

vi.mock("nuqs", () => ({
  parseAsString: {},
  useQueryState: () => [null, vi.fn()],
}));

vi.mock("@/client/custom-dashboard/custom-dashboard", () => {
  const mutation = () => ({ mutate: vi.fn(), isPending: false });
  return {
    getGetCustomDashboardQueryKey: (id: string) => [`/custom-dashboards/${id}`],
    getListCustomDashboardsQueryKey: () => ["/custom-dashboards"],
    useGetCustomDashboard: () => ({
      data: mocks.dashboard ? { data: mocks.dashboard } : undefined,
      isLoading: false,
      isError: mocks.error !== null,
      error: mocks.error,
      refetch: vi.fn(),
      isRefetching: false,
    }),
    useUpdateCustomDashboard: () => ({ mutate: mocks.update, isPending: false }),
    useDuplicateCustomDashboard: mutation,
    useDeleteCustomDashboard: mutation,
    useListCustomDashboardTemplates: () => ({ data: undefined }),
  };
});

vi.mock("@/client/chip/chip", () => ({
  useListChips: () => ({
    data: { data: { chips: [{ chip_id: "chip-1", installed_at: "2026-06-01T00:00:00Z" }] } },
  }),
  useGetChip: () => ({ data: { data: { chip_id: "chip-1", topology_id: "topo" } } }),
}));

vi.mock("@/client/metric-script/metric-script", () => ({
  evaluateMetricScript: mocks.evaluate,
  useListMetricScripts: () => ({ data: undefined, isLoading: false }),
  useGetMetricScript: () => ({ data: undefined, isLoading: false }),
}));

vi.mock("@/hooks/useTopologyConfig", async () => {
  const { TOPOLOGY: topology } =
    await import("@/components/features/metric-scripts/__tests__/fixtures");
  return { useTopologyConfig: () => topology };
});

vi.mock("@/hooks/useMetricsConfig", () => ({
  useMetricsConfig: () => ({ colorScale: { colors: [] }, qubitMetrics: [], couplingMetrics: [] }),
}));

vi.mock("@/components/selectors/ChipSelector", () => ({
  ChipSelector: ({ selectedChip }: { selectedChip: string }) => (
    <div data-testid="chip-selector">{selectedChip}</div>
  ),
}));

vi.mock("@/contexts/ProjectContext", () => ({
  useProject: () => ({ projectId: "project-1", canEdit: mocks.canEdit }),
}));

function markdownPanel(id: string, x: number, y: number): DashboardPanelResponse {
  return {
    panel_id: id,
    type: "markdown",
    title: `Panel ${id}`,
    layout: { x, y, w: 6, h: 2 },
    config: { content: `Content of ${id}` },
  };
}

function dashboard(overrides: Partial<CustomDashboardResponse> = {}): CustomDashboardResponse {
  return {
    dashboard_id: "dash-1",
    project_id: "project-1",
    name: "Collision review",
    description: "Weekly frequency review",
    visibility: "project",
    chip_id: "chip-1",
    // Stored out of reading order on purpose.
    panels: [markdownPanel("c", 0, 2), markdownPanel("b", 6, 0), markdownPanel("a", 0, 0)],
    owner_username: "alice",
    owner_user_id: "user-alice",
    can_edit: true,
    created_at: "2026-11-01T00:00:00Z",
    updated_at: "2026-11-02T00:00:00Z",
    ...overrides,
  };
}

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <CustomDashboardPageContent dashboardId="dash-1" />
    </QueryClientProvider>,
  );
}

function panelTitles(): string[] {
  return Array.from(
    screen.getByTestId("custom-dashboard-grid").querySelectorAll("section[aria-label]"),
  ).map((section) => section.getAttribute("aria-label") ?? "");
}

describe("CustomDashboardPageContent", () => {
  beforeEach(() => {
    mocks.canEdit = true;
    mocks.dashboard = dashboard();
    mocks.error = null;
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("renders panels in reading order (y, then x)", () => {
    renderPage();

    expect(screen.getByRole("heading", { name: "Collision review" })).toBeInTheDocument();
    expect(panelTitles()).toEqual(["Panel a", "Panel b", "Panel c"]);
    expect(screen.getByText("Content of b")).toBeInTheDocument();
    expect(screen.getByTestId("chip-selector")).toHaveTextContent("chip-1");
  });

  it("offers Edit, sharing and Delete when the caller may edit", () => {
    renderPage();

    expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Make private" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete dashboard" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Duplicate" })).toBeInTheDocument();
  });

  it("enters edit mode with panel menus and an unsaved badge after a layout change", async () => {
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));

    expect(screen.getByRole("toolbar", { name: "Edit dashboard" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    expect(screen.getAllByRole("button", { name: /^Panel actions for/ })).toHaveLength(3);
    expect(screen.queryByText("Unsaved changes")).not.toBeInTheDocument();

    fireEvent.keyDown(screen.getByRole("button", { name: "Panel actions for Panel a" }), {
      key: "Enter",
    });
    const moveRight = await screen.findByRole("menuitem", { name: "Move right" });
    fireEvent.click(moveRight);
    // Layout steps keep the menu open for repeated moves; close it to read the page.
    fireEvent.keyDown(moveRight, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("menu")).not.toBeInTheDocument());

    expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
    // Panel a moved into b's columns, so b is pushed below it.
    expect(screen.getByText("6×2 at 1,0")).toBeInTheDocument();
    expect(screen.getByText("6×2 at 6,2")).toBeInTheDocument();
  });

  it("shows Duplicate but not Edit or Delete to an editor who does not own it", () => {
    mocks.dashboard = dashboard({ can_edit: false });
    renderPage();

    expect(screen.getByRole("button", { name: "Duplicate" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete dashboard" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Make private" })).not.toBeInTheDocument();
  });

  it("is read-only for viewers even when the response allows editing", () => {
    mocks.canEdit = false;
    renderPage();

    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Duplicate" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Copy link" })).toBeInTheDocument();
  });

  it("shows a not-found state with a link back to the list on 404", () => {
    mocks.dashboard = null;
    mocks.error = Object.assign(new Error("Not found"), {
      isAxiosError: true,
      response: { status: 404, data: { detail: "Custom dashboard not found" } },
    });
    renderPage();

    expect(screen.getByText("Dashboard not found")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "All dashboards" })).toHaveAttribute(
      "href",
      "/custom-dashboards",
    );
  });

  it("evaluates a metric script panel at its pinned revision and offers a newer one", async () => {
    const { evaluateResponse, pairCell } =
      await import("@/components/features/metric-scripts/__tests__/fixtures");
    mocks.evaluate.mockResolvedValue({
      data: evaluateResponse(
        "pair",
        [
          pairCell("0", "1", { value: 99.2, assessment: { count: 6 } }),
          pairCell("1", "0", { status: "error", message: "KeyError" }),
        ],
        { params: { min_samples: 3 } },
      ),
    });
    mocks.dashboard = dashboard({
      panels: [
        {
          panel_id: "zx",
          type: "metric_script",
          title: "ZX90",
          layout: { x: 0, y: 0, w: 6, h: 4 },
          config: {
            script_id: "ms_1",
            metric_id: "zx90_median",
            script_revision: 2,
            period: { kind: "relative", days: 14 },
            params: {},
            view: "map",
            direction: "both",
            hops: [1],
          },
          script_name: "ZX90 median",
          latest_revision: 3,
        },
      ],
    });
    renderPage();

    expect(await screen.findByTestId("pair-map")).toBeInTheDocument();
    expect(mocks.evaluate).toHaveBeenCalledWith(
      "ms_1",
      {
        metric_id: "zx90_median",
        chip_id: "chip-1",
        period: { kind: "relative", days: 14 },
        params: {},
        revision: 2,
      },
      undefined,
      expect.anything(),
    );
    expect(screen.getByText("Newer revision r3 available")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Update to r3" })).not.toBeInTheDocument();
    expect(screen.getByTestId("metric-script-footer")).toHaveTextContent(
      "ZX90 median r2 · Median ZX90 gate fidelity · Last 14 days · min samples 3",
    );
    // The failed cell stays visible on the map.
    expect(screen.getByTestId("metric-edge-1>0")).toHaveAttribute("data-status", "error");

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.click(screen.getByRole("button", { name: "Update to r3" }));
    expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
    expect(screen.queryByText("Newer revision r3 available")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    const saved = mocks.update.mock.calls[0][0].data.panels[0];
    expect(saved.config.script_revision).toBe(3);
    // Response annotations are not sent back.
    expect(saved).not.toHaveProperty("script_name");
    expect(saved).not.toHaveProperty("latest_revision");
  });
});

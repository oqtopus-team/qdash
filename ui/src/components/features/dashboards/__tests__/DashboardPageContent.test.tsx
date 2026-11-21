import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { PageContextProvider } from "@/contexts/ChatDockContext";
import type { DashboardResponse, DashboardPanelResponse } from "@/schemas";

import { DashboardPageContent } from "../DashboardPageContent";

const mocks = vi.hoisted(() => ({
  canEdit: true,
  dashboard: null as unknown,
  error: null as unknown,
  scripts: [] as unknown[],
  update: vi.fn(),
  create: vi.fn(),
  evaluate: vi.fn(),
  evaluateDraft: vi.fn(),
  preview: null as unknown,
  previewError: null as unknown,
  previewedTemplates: [] as string[],
  replace: vi.fn(),
  toastError: vi.fn(),
  withDock: true,
  openGeneralChat: vi.fn(),
  provider: null as PageContextProvider | null,
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn(), replace: mocks.replace }),
}));

vi.mock("@/components/ui/Toast", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/components/ui/Toast")>();
  return {
    ...actual,
    useToast: () => ({ success: vi.fn(), error: mocks.toastError }),
  };
});

// The Agent panel's dock: the page registers its draft here and opens the panel through it.
vi.mock("@/contexts/ChatDockContext", () => ({
  useOptionalChatDock: () =>
    mocks.withDock
      ? {
          openGeneralChat: mocks.openGeneralChat,
          refreshPage: () => undefined,
          registerPage: (provider: PageContextProvider) => {
            mocks.provider = provider;
            return () => {
              if (mocks.provider === provider) mocks.provider = null;
            };
          },
        }
      : null,
}));

vi.mock("nuqs", () => ({
  parseAsString: {},
  useQueryState: () => [null, vi.fn()],
}));

vi.mock("@/client/dashboard/dashboard", () => {
  const mutation = () => ({ mutate: vi.fn(), isPending: false });
  return {
    getGetDashboardQueryKey: (id: string) => [`/dashboards/${id}`],
    getListDashboardsQueryKey: () => ["/dashboards"],
    useGetDashboard: () => ({
      data: mocks.dashboard ? { data: mocks.dashboard } : undefined,
      isLoading: false,
      isError: mocks.error !== null,
      error: mocks.error,
      refetch: vi.fn(),
      isRefetching: false,
    }),
    useUpdateDashboard: () => ({ mutate: mocks.update, isPending: false }),
    useCreateDashboard: () => ({ mutate: mocks.create, isPending: false }),
    useDuplicateDashboard: mutation,
    useDeleteDashboard: mutation,
    // A read-only GET: what Save would copy in from the template, nothing created.
    usePreviewDashboardTemplate: (templateId: string, options: { query: { enabled: boolean } }) => {
      if (options.query.enabled) mocks.previewedTemplates.push(templateId);
      return {
        data: options.query.enabled && mocks.preview ? { data: mocks.preview } : undefined,
        isLoading: false,
        isError: options.query.enabled && mocks.previewError !== null,
        error: mocks.previewError,
      };
    },
    useListDashboardTemplates: () => ({
      data: {
        data: {
          templates: [
            {
              template_id: "frequency-collision-map",
              name: "Frequency Collision Map",
              description: "Collision checks",
              panel_count: 9,
              panel_types: ["markdown", "metric_script"],
            },
          ],
        },
      },
    }),
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
  evaluateMetricScriptDraft: mocks.evaluateDraft,
  useListMetricScripts: () => ({
    data: { data: { scripts: mocks.scripts, total: mocks.scripts.length } },
    isLoading: false,
  }),
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

function dashboard(overrides: Partial<DashboardResponse> = {}): DashboardResponse {
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
    version: 7,
    created_at: "2026-11-01T00:00:00Z",
    updated_at: "2026-11-02T00:00:00Z",
    ...overrides,
  };
}

function renderPage(dashboardId: string | null = "dash-1") {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <DashboardPageContent dashboardId={dashboardId} />
    </QueryClientProvider>,
  );
}

function panelTitles(): string[] {
  return Array.from(
    screen.getByTestId("dashboard-grid").querySelectorAll("section[aria-label]"),
  ).map((section) => section.getAttribute("aria-label") ?? "");
}

describe("DashboardPageContent", () => {
  beforeEach(() => {
    mocks.canEdit = true;
    mocks.dashboard = dashboard();
    mocks.error = null;
    mocks.scripts = [];
    mocks.withDock = true;
    mocks.provider = null;
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

  it("offers Edit, sharing and Delete when the caller may edit", async () => {
    renderPage();

    expect(screen.getByRole("button", { name: "Edit" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Duplicate" })).toBeInTheDocument();

    // Sharing, settings and delete sit in the overflow menu next to Edit.
    fireEvent.keyDown(screen.getByRole("button", { name: "Dashboard actions" }), { key: "Enter" });
    expect(await screen.findByRole("menuitem", { name: "Make private" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Dashboard settings" })).toBeInTheDocument();
    expect(screen.getByRole("menuitem", { name: "Delete dashboard" })).toBeInTheDocument();
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

  it("saves panels against the version the edit started from and keeps the draft on 409", async () => {
    mocks.update.mockImplementation((_variables, options) =>
      options.onError({ response: { status: 409, data: { detail: "Dashboard was changed" } } }),
    );
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.keyDown(screen.getByRole("button", { name: "Panel actions for Panel a" }), {
      key: "Enter",
    });
    const moveRight = await screen.findByRole("menuitem", { name: "Move right" });
    fireEvent.click(moveRight);
    fireEvent.keyDown(moveRight, { key: "Escape" });
    await waitFor(() => expect(screen.queryByRole("menu")).not.toBeInTheDocument());
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(mocks.update).toHaveBeenCalledTimes(1);
    const [{ dashboardId, data }] = mocks.update.mock.calls[0];
    expect(dashboardId).toBe("dash-1");
    expect(data.expected_version).toBe(7);
    expect(data.panels).toHaveLength(3);
    // The rejected edit is still on screen, unsaved, for the user to keep or redo.
    expect(screen.getByRole("toolbar", { name: "Edit dashboard" })).toBeInTheDocument();
    expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
    expect(screen.getByText("6×2 at 1,0")).toBeInTheDocument();
  });

  it("shows Duplicate but not Edit or Delete to an editor who does not own it", () => {
    mocks.dashboard = dashboard({ can_edit: false });
    renderPage();

    expect(screen.getByRole("button", { name: "Duplicate" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Edit" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Dashboard actions" })).not.toBeInTheDocument();
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
      response: { status: 404, data: { detail: "Dashboard not found" } },
    });
    renderPage();

    expect(screen.getByText("Dashboard not found")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "All dashboards" })).toHaveAttribute(
      "href",
      "/dashboards",
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
    expect(screen.getByText("Update available")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Use updated definition" }),
    ).not.toBeInTheDocument();
    expect(screen.getByTestId("metric-script-footer")).toHaveTextContent(
      "ZX90 median r2 · Median ZX90 gate fidelity · Last 14 days · min samples 3",
    );
    // The failed cell stays visible on the map.
    expect(screen.getByTestId("metric-edge-1>0")).toHaveAttribute("data-status", "error");

    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.click(screen.getByRole("button", { name: "Use updated definition" }));
    expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
    expect(screen.queryByText("Update available")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    const saved = mocks.update.mock.calls[0][0].data.panels[0];
    expect(saved.config.script_revision).toBe(3);
    // Response annotations are not sent back.
    expect(saved).not.toHaveProperty("script_name");
    expect(saved).not.toHaveProperty("latest_revision");
  });

  function scriptPanel(scriptId: string): DashboardPanelResponse {
    return {
      panel_id: `panel-${scriptId}`,
      type: "metric_script",
      title: "Script panel",
      layout: { x: 0, y: 0, w: 6, h: 4 },
      config: {
        script_id: scriptId,
        metric_id: "m",
        script_revision: 1,
        period: { kind: "relative", days: 14 },
        params: {},
        view: "map",
        direction: "both",
        hops: [1],
      },
      script_name: scriptId,
      latest_revision: 1,
    };
  }

  function scriptSummary(overrides: Record<string, unknown>) {
    return {
      script_id: "ms_private",
      project_id: "project-1",
      name: "My private script",
      description: "",
      visibility: "private",
      status: "valid",
      revision: 1,
      active_revision: 1,
      metrics: [],
      template_id: null,
      owner_username: "alice",
      owner_user_id: "user-alice",
      can_edit: true,
      created_at: "",
      updated_at: "",
      ...overrides,
    };
  }

  it("explains which private scripts block sharing instead of sharing anything", async () => {
    mocks.evaluate.mockResolvedValue(new Promise(() => {}));
    mocks.scripts = [
      scriptSummary({}),
      scriptSummary({
        script_id: "ms_theirs",
        name: "Bob's script",
        owner_username: "bob",
        can_edit: false,
      }),
      scriptSummary({ script_id: "ms_shared", name: "Shared", visibility: "project" }),
    ];
    mocks.dashboard = dashboard({
      visibility: "private",
      panels: [scriptPanel("ms_private"), scriptPanel("ms_theirs"), scriptPanel("ms_shared")],
    });
    renderPage();

    fireEvent.keyDown(screen.getByRole("button", { name: "Dashboard actions" }), { key: "Enter" });
    fireEvent.click(await screen.findByRole("menuitem", { name: "Share with project" }));

    const dialog = await screen.findByRole("dialog", { name: "Share with project" });
    expect(mocks.update).not.toHaveBeenCalled();
    expect(dialog).toHaveTextContent("My private script");
    expect(dialog).toHaveTextContent("Bob's script");
    expect(dialog).not.toHaveTextContent("Shared");
    expect(screen.getByRole("link", { name: "Open script settings" })).toHaveAttribute(
      "href",
      "/dashboards/scripts/ms_private#metric-script-settings",
    );
    expect(dialog).toHaveTextContent("Ask bob to share it");
  });

  it("shows the server's reason when sharing is refused", async () => {
    mocks.update.mockImplementation((_variables, options) =>
      options.onError(
        Object.assign(new Error("Unprocessable"), {
          isAxiosError: true,
          response: {
            status: 422,
            data: {
              detail:
                "Invalid config for metric_script panel 'x': metric script 'Hidden' is private; share it with the project before using it on a shared dashboard",
            },
          },
        }),
      ),
    );
    mocks.dashboard = dashboard({ visibility: "private" });
    renderPage();

    fireEvent.keyDown(screen.getByRole("button", { name: "Dashboard actions" }), { key: "Enter" });
    fireEvent.click(await screen.findByRole("menuitem", { name: "Share with project" }));

    expect(mocks.update.mock.calls[0][0].data).toEqual({ visibility: "project" });
    const dialog = await screen.findByRole("dialog", { name: "Share with project" });
    expect(dialog).toHaveTextContent("metric script 'Hidden' is private");
  });
});

/** What the Agent reads from the page when a turn is sent. */
function agentPage() {
  if (!mocks.provider) throw new Error("the page did not register with the dock");
  return mocks.provider.current();
}

/** Apply a draft the Agent proposed, as the chat's Apply button does. */
function applyDraft(draft: unknown): boolean | void {
  if (!mocks.provider?.applyCode) throw new Error("the page takes no drafts");
  let result: boolean | void = undefined;
  act(() => {
    result = mocks.provider!.applyCode!(JSON.stringify(draft));
  });
  return result;
}

const STARTER_SOURCE = "# collision checks\n";

/** A template preview: a collision map and the reading guide, as the API returns them. */
function templatePreview({ existing = false }: { existing?: boolean } = {}) {
  return {
    template_id: "frequency-collision-map",
    name: "Frequency Collision Map",
    description: "Collision checks",
    panels: [
      {
        panel_id: "p-guide",
        type: "markdown",
        title: "Reading the collision maps",
        layout: { x: 6, y: 0, w: 6, h: 4 },
        config: { content: "Read the maps like this" },
      },
      {
        panel_id: "p-type1a",
        type: "metric_script",
        title: "Type1A — GE–GE proximity",
        layout: { x: 0, y: 0, w: 6, h: 4 },
        config: {
          ...(existing ? { script_id: "ms_collision", script_revision: 4 } : {}),
          metric_id: "Type1A",
          period: { kind: "relative", days: 30 },
          params: {},
          view: "map",
          direction: "both",
          hops: [1, 2],
        },
        script_name: existing ? "Frequency collision checks" : null,
        latest_revision: existing ? 4 : null,
        script_template_id: existing ? null : "collision",
      },
    ],
    scripts_to_create: existing
      ? []
      : [{ template_id: "collision", name: "Frequency collision checks", source: STARTER_SOURCE }],
  };
}

const proposedPanel = {
  panel_id: "new-note",
  type: "markdown",
  title: "How to read this",
  layout: { x: 0, y: 4, w: 12, h: 2 },
  config: { content: "Proposed note" },
};

describe("DashboardPageContent with the Agent", () => {
  beforeEach(() => {
    mocks.canEdit = true;
    mocks.dashboard = dashboard();
    mocks.error = null;
    mocks.scripts = [];
    mocks.withDock = true;
    mocks.provider = null;
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("opens the Agent panel with the dashboard's draft as context and changes nothing", () => {
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: "Edit with Agent" }));

    expect(mocks.openGeneralChat).toHaveBeenCalledTimes(1);
    expect(mocks.update).not.toHaveBeenCalled();
    expect(mocks.create).not.toHaveBeenCalled();
    // Opening does not enter edit mode either.
    expect(screen.queryByRole("toolbar", { name: "Edit dashboard" })).not.toBeInTheDocument();
    const page = agentPage();
    expect(page?.path).toBe("/dashboards/dash-1");
    expect(page?.dashboard).toMatchObject({
      dashboardId: "dash-1",
      name: "Collision review",
      visibility: "project",
      chipId: "chip-1",
      version: 7,
      dirty: false,
    });
    const draft = JSON.parse(page?.dashboard?.code ?? "");
    expect(Object.keys(draft)).toEqual(["panels"]);
    expect(draft.panels.map((panel: { panel_id: string }) => panel.panel_id)).toEqual([
      "c",
      "b",
      "a",
    ]);
    expect(mocks.provider?.suggestions?.()).toHaveLength(2);
  });

  it("shares only the route with members who cannot edit the dashboard", () => {
    mocks.dashboard = dashboard({ can_edit: false });
    renderPage();

    expect(screen.queryByRole("button", { name: "Edit with Agent" })).not.toBeInTheDocument();
    expect(agentPage()?.dashboard).toBeUndefined();
    expect(mocks.provider?.suggestions?.()).toEqual([]);
    // A proposal from an earlier chat cannot change their view.
    expect(applyDraft({ panels: [proposedPanel] })).toBe(false);
    expect(screen.queryByText("Proposed note")).not.toBeInTheDocument();
  });

  it("applies a proposed draft locally and saves it only on Save, against its version", () => {
    renderPage();

    expect(applyDraft({ panels: [...dashboard().panels, proposedPanel] })).toBe(true);

    expect(screen.getByRole("toolbar", { name: "Edit dashboard" })).toBeInTheDocument();
    expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
    expect(screen.getByText("Proposed note")).toBeInTheDocument();
    expect(mocks.update).not.toHaveBeenCalled();
    expect(agentPage()?.dashboard?.dirty).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(mocks.update).toHaveBeenCalledTimes(1);
    const [{ dashboardId, data }] = mocks.update.mock.calls[0];
    expect(dashboardId).toBe("dash-1");
    expect(data.expected_version).toBe(7);
    expect(data.panels).toHaveLength(4);
    expect(data).not.toHaveProperty("visibility");
  });

  it("reveals an applied draft at its edit toolbar when the Agent steps aside", () => {
    renderPage();

    // The dock applies first, then asks the page to reveal what it applied.
    expect(applyDraft({ panels: [...dashboard().panels, proposedPanel] })).toBe(true);
    act(() => mocks.provider?.revealAppliedCode?.());

    const toolbar = screen.getByRole("toolbar", { name: "Edit dashboard" });
    expect(toolbar).toHaveFocus();
    expect(toolbar).toHaveTextContent("Unsaved changes");
    // Revealing is not saving or sharing.
    expect(mocks.update).not.toHaveBeenCalled();
    expect(mocks.create).not.toHaveBeenCalled();
  });

  it("applies a draft on top of manual edits and keeps it when the save is stale", async () => {
    mocks.update.mockImplementation((_variables, options) =>
      options.onError({ response: { status: 409, data: { detail: "Dashboard was changed" } } }),
    );
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: "Edit" }));
    fireEvent.keyDown(screen.getByRole("button", { name: "Panel actions for Panel c" }), {
      key: "Enter",
    });
    fireEvent.click(await screen.findByRole("menuitem", { name: "Remove panel" }));
    await waitFor(() => expect(screen.queryByText("Content of c")).not.toBeInTheDocument());

    // The Agent reads the manual edit, so its proposal builds on it.
    const read = JSON.parse(agentPage()?.dashboard?.code ?? "");
    expect(read.panels.map((panel: { panel_id: string }) => panel.panel_id)).toEqual(["b", "a"]);
    expect(applyDraft({ panels: [...read.panels, proposedPanel] })).toBe(true);
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(mocks.update.mock.calls[0][0].data.expected_version).toBe(7);
    expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
    expect(screen.getByText("Proposed note")).toBeInTheDocument();
    expect(screen.queryByText("Content of c")).not.toBeInTheDocument();
  });

  it("refuses an invalid draft or one that changes sharing, and keeps the draft", () => {
    renderPage();

    expect(applyDraft({ panels: [proposedPanel], visibility: "project" })).toBe(false);
    expect(mocks.toastError).toHaveBeenLastCalledWith(
      "The proposed draft changes sharing; share the dashboard yourself from its actions",
    );
    expect(applyDraft({ panels: [{ ...proposedPanel, layout: { x: 8, y: 0, w: 6, h: 2 } }] })).toBe(
      false,
    );
    expect(mocks.provider?.applyCode?.("{not json")).toBe(false);

    expect(screen.queryByRole("toolbar", { name: "Edit dashboard" })).not.toBeInTheDocument();
    expect(screen.queryByText("Proposed note")).not.toBeInTheDocument();
    expect(mocks.update).not.toHaveBeenCalled();
  });

  it("offers the Agent first on an empty dashboard", () => {
    mocks.dashboard = dashboard({ panels: [] });
    renderPage();

    const ask = screen.getByRole("button", { name: "Ask Agent" });
    expect(ask).toHaveClass("btn-primary");
    expect(screen.getByRole("button", { name: "Add panel" })).not.toHaveClass("btn-primary");
    fireEvent.click(ask);
    expect(mocks.openGeneralChat).toHaveBeenCalledTimes(1);
    expect(mocks.provider?.suggestions?.()).toContain(
      "Show the median ZX90 fidelity per coupling over the last 14 days",
    );
  });

  it("keeps manual editing without the Agent panel", () => {
    mocks.withDock = false;
    mocks.dashboard = dashboard({ panels: [] });
    renderPage();

    expect(screen.queryByRole("button", { name: "Edit with Agent" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Ask Agent" })).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Add panel" })).toHaveLength(1);
  });

  it("stacks the header and wraps its actions when the content is narrow", () => {
    renderPage();

    const heading = screen.getByRole("heading", { name: "Collision review" });
    // A container query, so the Agent sidebar narrowing the page also stacks it.
    const container = heading.closest("div.\\@container");
    expect(container).toHaveClass("mb-4");
    expect(container?.firstElementChild).toHaveClass("flex-col", "@2xl:flex-row");
    expect(screen.getByRole("button", { name: "Edit with Agent" }).parentElement).toHaveClass(
      "flex-wrap",
    );
  });
});

describe("DashboardPageContent for a new dashboard", () => {
  beforeEach(() => {
    mocks.preview = null;
    mocks.previewError = null;
    mocks.previewedTemplates = [];
    mocks.canEdit = true;
    mocks.dashboard = null;
    mocks.error = null;
    mocks.scripts = [];
    mocks.withDock = true;
    mocks.provider = null;
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("starts as an empty local draft the Agent can read, without saving", () => {
    renderPage(null);

    expect(screen.getByRole("textbox", { name: "Dashboard name" })).toHaveValue("");
    expect(screen.getByText(/Draft, not saved yet/)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Done" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Save" })).toBeDisabled();
    const page = agentPage();
    expect(page?.path).toBe("/dashboards/new");
    expect(page?.dashboard?.dashboardId).toBeUndefined();
    expect(JSON.parse(page?.dashboard?.code ?? "")).toEqual({
      name: "",
      description: "",
      chip_id: null,
      template_id: null,
      panels: [],
    });
    expect(mocks.create).not.toHaveBeenCalled();
  });

  it("creates a private dashboard from an applied draft only on Save", () => {
    renderPage(null);

    expect(
      applyDraft({
        name: "ZX90 review",
        description: "Median fidelity",
        chip_id: "chip-1",
        template_id: null,
        panels: [proposedPanel],
      }),
    ).toBe(true);
    expect(screen.getByRole("textbox", { name: "Dashboard name" })).toHaveValue("ZX90 review");
    expect(screen.getByText("Proposed note")).toBeInTheDocument();
    expect(mocks.create).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(mocks.create).toHaveBeenCalledTimes(1);
    const [{ data }] = mocks.create.mock.calls[0];
    expect(data).toMatchObject({
      name: "ZX90 review",
      description: "Median fidelity",
      visibility: "private",
      chip_id: "chip-1",
    });
    expect(data.panels).toHaveLength(1);
    expect(data).not.toHaveProperty("template_id");
  });

  it("previews the suggested template's panels before Save and creates nothing until then", async () => {
    const { evaluateResponse, pairCell } =
      await import("@/components/features/metric-scripts/__tests__/fixtures");
    mocks.evaluateDraft.mockResolvedValue({
      data: evaluateResponse("pair", [pairCell("0", "1", { value: 1.5 })]),
    });
    mocks.preview = templatePreview();
    mocks.create.mockImplementation((_variables, options) =>
      options.onSuccess({ data: { dashboard_id: "dash-9", name: "Collisions" } }),
    );
    renderPage(null);
    expect(mocks.previewedTemplates).toEqual([]);

    // The Agent's answer to the first suggestion: the starter template, no panels of its own.
    expect(
      applyDraft({ name: "Collisions", template_id: "frequency-collision-map", panels: [] }),
    ).toBe(true);
    expect(mocks.previewedTemplates).toContain("frequency-collision-map");
    const status = screen.getByRole("status");
    expect(status).toHaveTextContent(
      "Preview of the Frequency Collision Map template (9 panels). Nothing is created until you save",
    );
    expect(status).toHaveTextContent(
      "Save also adds the metric script Frequency collision checks, shared with the project",
    );
    // The panels Save would create, reviewable now.
    const grid = screen.getByTestId("template-preview-grid");
    expect(
      Array.from(grid.querySelectorAll("section[aria-label]")).map((section) =>
        section.getAttribute("aria-label"),
      ),
    ).toEqual(["Type1A — GE–GE proximity", "Reading the collision maps"]);
    expect(screen.getByText("Read the maps like this")).toBeInTheDocument();
    // The script panel runs the starter source as an unsaved draft: real results, nothing stored.
    expect(await screen.findByTestId("pair-map")).toBeInTheDocument();
    expect(mocks.evaluateDraft).toHaveBeenCalledWith(
      expect.objectContaining({
        source: STARTER_SOURCE,
        metric_id: "Type1A",
        chip_id: "chip-1",
        period: { kind: "relative", days: 30 },
      }),
      undefined,
      expect.anything(),
    );
    expect(mocks.evaluate).not.toHaveBeenCalled();
    expect(screen.getByTestId("metric-script-footer")).toHaveTextContent(
      "Frequency collision checks (added on save)",
    );
    // Applying and previewing wrote nothing and shared nothing.
    expect(mocks.create).not.toHaveBeenCalled();
    expect(mocks.update).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(mocks.create).toHaveBeenCalledTimes(1);
    expect(mocks.create.mock.calls[0][0].data).toMatchObject({
      template_id: "frequency-collision-map",
      panels: [],
      visibility: "private",
    });
    expect(mocks.replace).toHaveBeenCalledWith("/dashboards/dash-9");
  });

  it("pins previewed script panels to the project's script when it already exists", async () => {
    mocks.evaluate.mockResolvedValue(new Promise(() => {}));
    mocks.preview = templatePreview({ existing: true });
    renderPage(null);

    applyDraft({ name: "Collisions", template_id: "frequency-collision-map", panels: [] });

    expect(screen.getByRole("status")).not.toHaveTextContent("Save also adds");
    await waitFor(() => expect(mocks.evaluate).toHaveBeenCalled());
    expect(mocks.evaluate.mock.calls[0][0]).toBe("ms_collision");
    expect(mocks.evaluate.mock.calls[0][1]).toMatchObject({ metric_id: "Type1A", revision: 4 });
    expect(mocks.evaluateDraft).not.toHaveBeenCalled();
  });

  it("keeps the template draft and its preview when QDash refuses the Save", () => {
    mocks.evaluateDraft.mockResolvedValue(new Promise(() => {}));
    mocks.preview = templatePreview();
    mocks.create.mockImplementation((_variables, options) =>
      options.onError({ response: { status: 500, data: { detail: "database unavailable" } } }),
    );
    renderPage(null);
    applyDraft({ name: "Collisions", template_id: "frequency-collision-map", panels: [] });

    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(mocks.create).toHaveBeenCalledTimes(1);
    expect(mocks.toastError).toHaveBeenCalledWith("database unavailable");
    expect(mocks.replace).not.toHaveBeenCalled();
    expect(screen.getByTestId("template-preview-grid")).toBeInTheDocument();
    expect(screen.getByRole("textbox", { name: "Dashboard name" })).toHaveValue("Collisions");
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
    expect(JSON.parse(agentPage()?.dashboard?.code ?? "")).toMatchObject({
      template_id: "frequency-collision-map",
      panels: [],
    });
  });

  it("says why the template preview is missing and still allows Save", () => {
    mocks.preview = null;
    mocks.previewError = { response: { status: 404, data: { detail: "Unknown template" } } };
    renderPage(null);
    applyDraft({ name: "Collisions", template_id: "frequency-collision-map", panels: [] });

    expect(screen.getByRole("alert")).toHaveTextContent("Unknown template");
    expect(screen.getByRole("button", { name: "Save" })).toBeEnabled();
  });

  it("asks for a name before creating, and keeps the draft when QDash refuses it", () => {
    mocks.create.mockImplementation((_variables, options) =>
      options.onError({ response: { status: 422, data: { detail: "panel 'x' is invalid" } } }),
    );
    renderPage(null);
    applyDraft({ panels: [proposedPanel] });

    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(mocks.create).not.toHaveBeenCalled();
    expect(screen.getByText("Name the dashboard before saving")).toBeInTheDocument();

    fireEvent.change(screen.getByRole("textbox", { name: "Dashboard name" }), {
      target: { value: "Mine" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(mocks.create).toHaveBeenCalledTimes(1);
    expect(mocks.replace).not.toHaveBeenCalled();
    expect(screen.getByText("Proposed note")).toBeInTheDocument();
    expect(screen.getByText("Unsaved changes")).toBeInTheDocument();
  });

  it("is not offered to members who cannot create dashboards", () => {
    mocks.canEdit = false;
    renderPage(null);

    expect(screen.getByText("You cannot create dashboards")).toBeInTheDocument();
    expect(screen.queryByRole("textbox", { name: "Dashboard name" })).not.toBeInTheDocument();
  });
});

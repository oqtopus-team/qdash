import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { CustomDashboardResponse, MetricScriptSummary } from "@/schemas";

import { CustomDashboardListPageContent } from "../CustomDashboardListPageContent";

const mocks = vi.hoisted(() => ({
  canEdit: true,
  tab: null as string | null,
  dashboards: [] as unknown[],
  scripts: [] as unknown[],
  create: vi.fn(),
  createScript: vi.fn(),
  copyScript: vi.fn(),
  deleteScript: vi.fn(),
  push: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mocks.push }),
}));

vi.mock("nuqs", async () => {
  const { useState } = await import("react");
  return {
    parseAsStringLiteral: () => ({ withDefault: (value: string) => ({ defaultValue: value }) }),
    useQueryState: (_key: string, parser: { defaultValue: string }) => {
      const [value, setValue] = useState<string | null>(mocks.tab);
      return [value ?? parser.defaultValue, (next: string | null) => setValue(next)];
    },
  };
});

vi.mock("@/client/metric-script/metric-script", () => {
  const mutation = (mutate: unknown) => () => ({ mutate, isPending: false, variables: undefined });
  return {
    getListMetricScriptsQueryKey: () => ["/metric-scripts"],
    useListMetricScripts: () => ({
      data: { data: { scripts: mocks.scripts, total: mocks.scripts.length } },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
      isRefetching: false,
    }),
    useListMetricScriptTemplates: () => ({
      data: {
        data: {
          templates: [
            {
              template_id: "zx90_median",
              name: "Median ZX90 fidelity",
              description: "Median of raw ZX90 observations per coupling",
              source: "",
            },
          ],
        },
      },
      isLoading: false,
    }),
    useCreateMetricScript: mutation(mocks.createScript),
    useCopyMetricScript: mutation(mocks.copyScript),
    useDeleteMetricScript: mutation(mocks.deleteScript),
  };
});

vi.mock("@/client/custom-dashboard/custom-dashboard", () => {
  const mutation = () => ({ mutate: vi.fn(), isPending: false, variables: undefined });
  return {
    getListCustomDashboardsQueryKey: () => ["/custom-dashboards"],
    useListCustomDashboards: () => ({
      data: { data: { dashboards: mocks.dashboards, total: mocks.dashboards.length } },
      isLoading: false,
      isError: false,
      error: null,
      refetch: vi.fn(),
      isRefetching: false,
    }),
    useCreateCustomDashboard: () => ({
      mutate: mocks.create,
      isPending: false,
      variables: undefined,
    }),
    useDuplicateCustomDashboard: mutation,
    useDeleteCustomDashboard: mutation,
    useListCustomDashboardTemplates: () => ({
      data: {
        data: {
          templates: [
            {
              template_id: "frequency-collision-map",
              name: "Frequency Collision Map",
              description: "Collision checks on the topology",
              panel_count: 8,
              panel_types: ["collision_check", "markdown", "qubit_metric"],
            },
          ],
        },
      },
    }),
  };
});

vi.mock("@/client/chip/chip", () => ({
  useListChips: () => ({ data: { data: { chips: [] } } }),
}));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: { user_id: "user-me", username: "me" } }),
}));

vi.mock("@/contexts/ProjectContext", () => ({
  useProject: () => ({ projectId: "project-1", canEdit: mocks.canEdit }),
}));

function dashboard(overrides: Partial<CustomDashboardResponse>): CustomDashboardResponse {
  return {
    dashboard_id: "d",
    project_id: "project-1",
    name: "Dashboard",
    description: "",
    visibility: "private",
    chip_id: "chip-1",
    panels: [],
    owner_username: "me",
    owner_user_id: "user-me",
    can_edit: true,
    version: 0,
    created_at: "2026-11-01T00:00:00Z",
    updated_at: "2026-11-02T00:00:00Z",
    ...overrides,
  };
}

function script(overrides: Partial<MetricScriptSummary>): MetricScriptSummary {
  return {
    script_id: "ms_1",
    project_id: "project-1",
    name: "Script",
    description: "",
    visibility: "private",
    status: "valid",
    revision: 1,
    active_revision: 1,
    metrics: [],
    template_id: null,
    owner_username: "me",
    owner_user_id: "user-me",
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
      <CustomDashboardListPageContent />
    </QueryClientProvider>,
  );
}

describe("CustomDashboardListPageContent", () => {
  beforeEach(() => {
    mocks.canEdit = true;
    mocks.tab = null;
    mocks.scripts = [
      script({
        script_id: "ms_mine",
        name: "ZX90 median",
        metrics: [
          { id: "zx90", title: "ZX90", unit: "%", target: "pair" },
          { id: "t1", title: "T1", unit: "us", target: "qubit" },
        ],
      }),
      script({
        script_id: "ms_team",
        name: "Team collisions",
        visibility: "project",
        status: "invalid",
        revision: 4,
        active_revision: 3,
        owner_username: "alice",
        owner_user_id: "user-alice",
        can_edit: false,
      }),
      script({
        script_id: "ms_draft",
        name: "Draft",
        status: "invalid",
        active_revision: null,
      }),
    ];
    mocks.dashboards = [
      dashboard({ dashboard_id: "mine-private", name: "My private board" }),
      dashboard({ dashboard_id: "mine-shared", name: "My shared board", visibility: "project" }),
      dashboard({
        dashboard_id: "theirs",
        name: "Team board",
        visibility: "project",
        owner_username: "alice",
        owner_user_id: "user-alice",
        can_edit: false,
      }),
    ];
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("creates a dashboard from the Frequency Collision Map template", () => {
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: "New dashboard" }));

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Collisions" } });
    expect(screen.getByRole("radio", { name: /Blank dashboard/ })).toBeChecked();
    fireEvent.click(screen.getByRole("radio", { name: /Frequency Collision Map/ }));
    fireEvent.click(screen.getByRole("button", { name: "Create dashboard" }));

    expect(mocks.create).toHaveBeenCalledTimes(1);
    expect(mocks.create.mock.calls[0][0]).toEqual({
      data: {
        name: "Collisions",
        description: "",
        visibility: "private",
        chip_id: null,
        template_id: "frequency-collision-map",
        panels: [],
      },
    });
  });

  it("creates a blank dashboard without a template", () => {
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: "New dashboard" }));
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Empty" } });
    fireEvent.click(screen.getByRole("button", { name: "Create dashboard" }));

    expect(mocks.create.mock.calls[0][0].data).toMatchObject({ name: "Empty", template_id: null });
  });

  it("groups own dashboards under Mine and others' shared ones under Shared with project", () => {
    renderPage();

    const mine = screen.getByRole("region", { name: /Mine/ });
    const shared = screen.getByRole("region", { name: /Shared with project/ });

    expect(within(mine).getByRole("link", { name: "My private board" })).toBeInTheDocument();
    expect(within(mine).getByRole("link", { name: "My shared board" })).toBeInTheDocument();
    expect(within(mine).queryByText("Team board")).not.toBeInTheDocument();
    expect(within(shared).getByRole("link", { name: "Team board" })).toBeInTheDocument();
    expect(within(shared).getByText("by alice")).toBeInTheDocument();
  });

  it("lets editors create and duplicate, but delete only dashboards they may edit", () => {
    renderPage();

    expect(screen.getByRole("button", { name: "New dashboard" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Duplicate Team board" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete My private board" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Delete Team board" })).not.toBeInTheDocument();
  });

  it("hides New, Duplicate and Delete from viewers", () => {
    mocks.canEdit = false;
    renderPage();

    expect(screen.queryByRole("button", { name: "New dashboard" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Duplicate/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Delete/ })).not.toBeInTheDocument();
    expect(screen.getAllByRole("link", { name: "Open" })).toHaveLength(3);
  });

  it("shows an empty state when no dashboard is visible", () => {
    mocks.dashboards = [];
    renderPage();

    expect(screen.getByText("No dashboards yet")).toBeInTheDocument();
  });
});

describe("CustomDashboardListPageContent scripts tab", () => {
  beforeEach(() => {
    mocks.canEdit = true;
    mocks.tab = null;
    mocks.dashboards = [];
    mocks.scripts = [
      script({
        script_id: "ms_mine",
        name: "ZX90 median",
        metrics: [
          { id: "zx90", title: "ZX90", unit: "%", target: "pair" },
          { id: "t1", title: "T1", unit: "us", target: "qubit" },
        ],
      }),
      script({
        script_id: "ms_team",
        name: "Team collisions",
        visibility: "project",
        status: "invalid",
        revision: 4,
        active_revision: 3,
        owner_username: "alice",
        owner_user_id: "user-alice",
        can_edit: false,
      }),
      script({ script_id: "ms_draft", name: "Draft", status: "invalid", active_revision: null }),
    ];
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("switches between dashboards and scripts", () => {
    renderPage();

    expect(screen.getByRole("tab", { name: "Dashboards" })).toHaveAttribute(
      "aria-selected",
      "true",
    );
    expect(screen.getAllByRole("button", { name: "New dashboard" }).length).toBeGreaterThan(0);

    fireEvent.click(screen.getByRole("tab", { name: "Scripts" }));

    expect(screen.getByRole("tab", { name: "Scripts" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("button", { name: "New script" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "New dashboard" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "ZX90 median" })).toHaveAttribute(
      "href",
      "/custom-dashboards/scripts/ms_mine",
    );
  });

  it("lists scripts with owner, visibility, status and metrics", () => {
    mocks.tab = "scripts";
    renderPage();

    const mine = screen.getByRole("region", { name: /My scripts/ });
    const shared = screen.getByRole("region", { name: /Shared scripts/ });
    expect(within(mine).getByText("Valid r1")).toBeInTheDocument();
    expect(within(mine).getByText("2 metrics · pair, qubit")).toBeInTheDocument();
    expect(within(mine).getByText("Invalid r1")).toBeInTheDocument();
    expect(within(shared).getByText("Invalid r4 · active r3")).toBeInTheDocument();
    expect(within(shared).getByText("by alice")).toBeInTheDocument();
    expect(within(shared).getByText("Shared with project")).toBeInTheDocument();

    // Copy needs a valid revision; delete needs edit rights on the script.
    expect(screen.getByRole("button", { name: "Copy Team collisions" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Copy Draft" })).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "Delete Team collisions" }),
    ).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Delete ZX90 median" })).toBeInTheDocument();
  });

  it("creates a script from a template", () => {
    mocks.tab = "scripts";
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: "New script" }));

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "ZX90" } });
    fireEvent.click(screen.getByRole("radio", { name: /Median ZX90 fidelity/ }));
    fireEvent.click(screen.getByRole("radio", { name: /Shared with project/ }));
    fireEvent.click(screen.getByRole("button", { name: "Create script" }));

    expect(mocks.createScript.mock.calls[0][0]).toEqual({
      data: { name: "ZX90", description: "", visibility: "project", template_id: "zx90_median" },
    });
  });

  it("creates a blank script with starter source", () => {
    mocks.tab = "scripts";
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: "New script" }));
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Mine" } });
    fireEvent.click(screen.getByRole("button", { name: "Create script" }));

    const data = mocks.createScript.mock.calls[0][0].data;
    expect(data).toMatchObject({ name: "Mine", visibility: "private" });
    expect(data.source).toContain("from qdash_metrics import metric");
    expect(data).not.toHaveProperty("template_id");
  });

  it("shows which dashboards block a delete", async () => {
    mocks.tab = "scripts";
    mocks.deleteScript.mockImplementation(
      (_variables: unknown, options: { onError: (error: unknown) => void }) =>
        options.onError({
          response: {
            status: 409,
            data: { detail: "Dashboards still use this script: 'Weekly review'" },
          },
        }),
    );
    renderPage();

    fireEvent.click(screen.getByRole("button", { name: "Delete ZX90 median" }));
    fireEvent.click(screen.getByRole("button", { name: "Delete" }));

    await waitFor(() =>
      expect(screen.getByRole("alert")).toHaveTextContent(
        "Dashboards still use this script: 'Weekly review'",
      ),
    );
    expect(mocks.deleteScript.mock.calls[0][0]).toEqual({ scriptId: "ms_mine" });
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("hides New script, Copy and Delete from viewers", () => {
    mocks.canEdit = false;
    mocks.tab = "scripts";
    renderPage();

    expect(screen.queryByRole("button", { name: "New script" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Copy/ })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /^Delete/ })).not.toBeInTheDocument();
  });
});

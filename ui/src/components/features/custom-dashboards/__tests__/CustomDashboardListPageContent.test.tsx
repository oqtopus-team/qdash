import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { CustomDashboardResponse } from "@/schemas";

import { CustomDashboardListPageContent } from "../CustomDashboardListPageContent";

const mocks = vi.hoisted(() => ({
  canEdit: true,
  dashboards: [] as unknown[],
  create: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

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
    mocks.create.mockReset();
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

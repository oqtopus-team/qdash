import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { CustomDashboardTemplateResponse } from "@/schemas";

import { DashboardFormDialog } from "../DashboardFormDialog";

const COLLISION: CustomDashboardTemplateResponse = {
  template_id: "frequency-collision-map",
  name: "Frequency Collision Map",
  description: "Collision checks on the topology",
  panel_count: 8,
  panel_types: ["markdown", "metric_script", "qubit_metric"],
};

const templatesQuery = vi.hoisted(() => ({
  state: {
    data: undefined as { data: { templates: CustomDashboardTemplateResponse[] } } | undefined,
    isLoading: true,
    isError: false,
    isFetching: false,
    error: null as unknown,
    refetch: vi.fn(),
  },
  listeners: new Set<() => void>(),
  set(patch: Partial<(typeof templatesQuery)["state"]>) {
    Object.assign(templatesQuery.state, patch);
    for (const listener of templatesQuery.listeners) listener();
  },
}));

vi.mock("@/client/custom-dashboard/custom-dashboard", async () => {
  const { useEffect, useReducer } = await import("react");
  return {
    useListCustomDashboardTemplates: () => {
      const [, rerender] = useReducer((n: number) => n + 1, 0);
      useEffect(() => {
        templatesQuery.listeners.add(rerender);
        return () => {
          templatesQuery.listeners.delete(rerender);
        };
      }, []);
      return { ...templatesQuery.state };
    },
  };
});

vi.mock("@/client/chip/chip", () => ({
  useListChips: () => ({
    data: {
      data: {
        chips: [
          { chip_id: "chip-old", installed_at: "2026-01-01T00:00:00Z", activity_status: "active" },
          { chip_id: "chip-new", installed_at: "2026-06-01T00:00:00Z", activity_status: "active" },
        ],
      },
    },
  }),
}));

function renderCreate() {
  const onSubmit = vi.fn();
  render(
    <DashboardFormDialog
      open
      mode="create"
      pending={false}
      error={null}
      onOpenChange={vi.fn()}
      onSubmit={onSubmit}
    />,
  );
  return onSubmit;
}

describe("DashboardFormDialog (create)", () => {
  beforeEach(() => {
    templatesQuery.set({
      data: undefined,
      isLoading: true,
      isError: false,
      isFetching: false,
      error: null,
    });
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("waits for templates, then defaults to the first one and names the dashboard after it", () => {
    const onSubmit = renderCreate();

    expect(screen.getByLabelText("Loading templates")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "" } });
    // Nothing is created on the user's behalf before the choice is known.
    expect(screen.getByRole("button", { name: "Create dashboard" })).toBeDisabled();

    act(() => templatesQuery.set({ data: { data: { templates: [COLLISION] } }, isLoading: false }));

    expect(screen.getByRole("radio", { name: /Frequency Collision Map/ })).toBeChecked();
    expect(screen.getByRole("radio", { name: /Blank dashboard/ })).not.toBeChecked();
    expect(screen.getByLabelText("Name")).toHaveValue("Frequency Collision Map");
    // The newest chip is preselected and sharing stays private.
    expect(screen.getByLabelText("Chip")).toHaveValue("chip-new");
    expect(screen.getByRole("radio", { name: /Private/ })).toBeChecked();

    fireEvent.click(screen.getByRole("button", { name: "Create dashboard" }));
    expect(onSubmit).toHaveBeenCalledWith({
      name: "Frequency Collision Map",
      description: "",
      visibility: "private",
      chip_id: "chip-new",
      template_id: "frequency-collision-map",
    });
  });

  it("keeps a name the user typed when the template choice changes", () => {
    const onSubmit = renderCreate();
    act(() => templatesQuery.set({ data: { data: { templates: [COLLISION] } }, isLoading: false }));

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Cool-down 12" } });
    fireEvent.click(screen.getByRole("radio", { name: /Blank dashboard/ }));
    expect(screen.getByLabelText("Name")).toHaveValue("Cool-down 12");
    fireEvent.click(screen.getByRole("radio", { name: /Frequency Collision Map/ }));
    expect(screen.getByLabelText("Name")).toHaveValue("Cool-down 12");

    fireEvent.click(screen.getByRole("radio", { name: /Blank dashboard/ }));
    fireEvent.click(screen.getByRole("button", { name: "Create dashboard" }));
    expect(onSubmit.mock.calls[0][0]).toMatchObject({ name: "Cool-down 12", template_id: null });
  });

  it("refills the name from the template after the user clears it", () => {
    renderCreate();
    act(() => templatesQuery.set({ data: { data: { templates: [COLLISION] } }, isLoading: false }));

    fireEvent.click(screen.getByRole("radio", { name: /Blank dashboard/ }));
    expect(screen.getByLabelText("Name")).toHaveValue("");
    fireEvent.click(screen.getByRole("radio", { name: /Frequency Collision Map/ }));
    expect(screen.getByLabelText("Name")).toHaveValue("Frequency Collision Map");
  });

  it("falls back to an explicit blank start when templates fail to load", () => {
    const onSubmit = renderCreate();
    act(() =>
      templatesQuery.set({
        isLoading: false,
        isError: true,
        error: { response: { data: { detail: "Template service unavailable" } } },
      }),
    );

    expect(screen.getByRole("alert")).toHaveTextContent("Template service unavailable");
    expect(screen.getByRole("radio", { name: /Blank dashboard/ })).toBeChecked();
    fireEvent.click(screen.getByRole("button", { name: "try again" }));
    expect(templatesQuery.state.refetch).toHaveBeenCalledTimes(1);

    fireEvent.change(screen.getByLabelText("Name"), { target: { value: "Manual" } });
    fireEvent.click(screen.getByRole("button", { name: "Create dashboard" }));
    expect(onSubmit.mock.calls[0][0]).toMatchObject({ name: "Manual", template_id: null });
  });

  it("explains when no template exists", () => {
    renderCreate();
    act(() => templatesQuery.set({ data: { data: { templates: [] } }, isLoading: false }));

    expect(screen.getByText("No templates are available in this project")).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /Blank dashboard/ })).toBeChecked();
  });

  it("keeps the description behind a disclosure that submits its text", () => {
    const onSubmit = renderCreate();
    act(() => templatesQuery.set({ data: { data: { templates: [COLLISION] } }, isLoading: false }));

    const disclosure = screen.getByText("Add a description").closest("details");
    expect(disclosure).not.toHaveAttribute("open");
    fireEvent.click(screen.getByText("Add a description"));
    fireEvent.change(screen.getByLabelText("Description"), {
      target: { value: "Weekly collision review" },
    });
    fireEvent.click(screen.getByRole("radio", { name: /Shared with project/ }));
    fireEvent.click(screen.getByRole("button", { name: "Create dashboard" }));

    expect(onSubmit.mock.calls[0][0]).toMatchObject({
      description: "Weekly collision review",
      visibility: "project",
    });
  });
});

describe("DashboardFormDialog (edit)", () => {
  afterEach(() => {
    cleanup();
  });

  it("shows the saved values without the template step", () => {
    const onSubmit = vi.fn();
    render(
      <DashboardFormDialog
        open
        mode="edit"
        initial={{
          name: "Board",
          description: "Notes",
          visibility: "project",
          chip_id: "chip-old",
        }}
        pending={false}
        error={null}
        onOpenChange={vi.fn()}
        onSubmit={onSubmit}
      />,
    );

    expect(screen.queryByText("Start from")).not.toBeInTheDocument();
    expect(screen.getByLabelText("Description")).toHaveValue("Notes");
    expect(screen.getByLabelText("Default chip")).toHaveValue("chip-old");
    fireEvent.click(screen.getByRole("button", { name: "Save settings" }));
    expect(onSubmit).toHaveBeenCalledWith({
      name: "Board",
      description: "Notes",
      visibility: "project",
      chip_id: "chip-old",
    });
  });
});

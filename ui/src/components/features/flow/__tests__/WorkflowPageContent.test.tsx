import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { WorkflowPageContent } from "@/components/features/flow/WorkflowPageContent";

function flow(name: string, created_by: string, folder = "", tags: string[] = []) {
  return {
    name,
    created_by,
    description: "",
    chip_id: "chip1",
    flow_function_name: "main",
    created_at: "2026-10-01T00:00:00Z",
    updated_at: "2026-10-02T00:00:00Z",
    tags,
    folder,
  };
}

const mocks = vi.hoisted(() => ({
  flows: [] as ReturnType<typeof flow>[],
  listFlows: vi.fn(),
  deleteFlow: vi.fn(),
  canEdit: true,
  toastSuccess: vi.fn(),
  toastError: vi.fn(),
}));

vi.mock("@/client/flow/flow", () => ({
  listFlows: mocks.listFlows,
  deleteFlow: mocks.deleteFlow,
}));
vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ username: "mia" }),
}));
vi.mock("@/contexts/ProjectContext", () => ({
  useProject: () => ({ canEdit: mocks.canEdit }),
}));
vi.mock("@/components/ui/Toast", () => ({
  useToast: () => ({ success: mocks.toastSuccess, error: mocks.toastError }),
}));
vi.mock("@/components/features/flow/FlowSchedulesSection", () => ({
  FlowSchedulesSection: () => <div data-testid="schedules" />,
}));
vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: React.ComponentProps<"a">) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={client}>
      <WorkflowPageContent />
    </QueryClientProvider>,
  );
}

/** The table and the narrow-screen cards both render in jsdom; the table comes first. */
function first(elements: HTMLElement[]): HTMLElement {
  return elements[0]!;
}

function selectBox(name: string) {
  return first(screen.getAllByRole("checkbox", { name: `Select workflow ${name}` }));
}

function deleteButton(name: string) {
  return first(screen.getAllByRole("button", { name: `Delete workflow ${name}` }));
}

beforeEach(() => {
  mocks.canEdit = true;
  mocks.flows = [
    flow("zoe_flow", "zoe"),
    flow("my_flow", "mia", "", ["t1"]),
    flow("daily_flow", "mia", "daily/t1"),
  ];
  mocks.listFlows.mockImplementation(async () => ({ data: { flows: [...mocks.flows] } }));
  // A successful delete removes the flow from what the server lists next.
  mocks.deleteFlow.mockImplementation(async (name: string) => {
    mocks.flows = mocks.flows.filter((item) => item.name !== name);
    return { data: { message: "ok" } };
  });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("WorkflowPageContent", () => {
  it("shows one folder per creator, the signed-in user's first and the only one open", async () => {
    renderPage();
    await screen.findByTestId("flow-folder-mia");
    const folders = screen.getAllByTestId(/^flow-folder-/);
    expect(folders.map((el) => el.getAttribute("data-testid"))).toEqual([
      "flow-folder-mia",
      "flow-folder-zoe",
    ]);
    expect(folders[0]).toHaveAttribute("open");
    expect(folders[1]).not.toHaveAttribute("open");

    const mine = within(folders[0]!);
    expect(mine.getByText("You")).toBeInTheDocument();
    expect(mine.getByText("2 workflows")).toBeInTheDocument();
    expect(mine.getAllByRole("link", { name: /my_flow/ })[0]).toHaveAttribute(
      "href",
      "/workflow/my_flow",
    );
    expect(mine.queryByText("zoe_flow")).toBeNull();
    expect(within(folders[1]!).queryByText("You")).toBeNull();
    // Each space opens in the editor's Explorer through its first flow.
    expect(within(folders[1]!).getByRole("link", { name: /Open in editor/ })).toHaveAttribute(
      "href",
      "/workflow/zoe_flow?space=zoe",
    );
    // The subfolder path becomes nested, open disclosures with their own counts.
    const daily = mine.getByTestId("flow-subfolder-daily");
    expect(daily).toHaveAttribute("open");
    expect(within(daily).getByTestId("flow-subfolder-daily/t1")).toHaveAttribute("open");
    expect(within(daily).getAllByRole("link", { name: /daily_flow/ }).length).toBeGreaterThan(0);
  });

  it("keeps selection and delete controls outside the navigation links", async () => {
    renderPage();
    await screen.findByTestId("flow-folder-mia");
    for (const control of [
      ...screen.getAllByRole("checkbox", { name: "Select workflow my_flow" }),
      ...screen.getAllByRole("button", { name: "Delete workflow my_flow" }),
    ]) {
      expect(control.closest("a")).toBeNull();
    }
    // Card and table both still link to the editor.
    for (const link of screen.getAllByRole("link", { name: "my_flow" })) {
      expect(link).toHaveAttribute("href", "/workflow/my_flow");
    }
  });

  it("hides selection and deletion from users who cannot edit", async () => {
    mocks.canEdit = false;
    renderPage();
    await screen.findByTestId("flow-folder-mia");
    expect(screen.queryAllByRole("checkbox")).toHaveLength(0);
    expect(screen.queryByRole("button", { name: /Delete/ })).toBeNull();
  });

  it("selects every listed workflow, counts the selection, and clears it", async () => {
    renderPage();
    await screen.findByTestId("flow-folder-mia");
    const selectAll = screen.getByRole("checkbox", { name: "Select all 3 workflows" });
    const deleteSelected = screen.getByRole("button", { name: "Delete selected" });
    expect(screen.getByText("0 selected")).toBeInTheDocument();
    expect(deleteSelected).toBeDisabled();

    fireEvent.click(selectBox("my_flow"));
    expect(screen.getByText("1 selected")).toBeInTheDocument();
    expect((selectAll as HTMLInputElement).indeterminate).toBe(true);
    expect(deleteSelected).toBeEnabled();

    fireEvent.click(selectAll);
    expect(screen.getByText("3 selected")).toBeInTheDocument();
    // Flows in the closed folder of another creator are included.
    expect(selectBox("zoe_flow")).toBeChecked();

    fireEvent.click(screen.getByRole("button", { name: "Clear" }));
    expect(screen.getByText("0 selected")).toBeInTheDocument();
    expect(selectBox("my_flow")).not.toBeChecked();
  });

  it("asks before deleting one workflow and does nothing on cancel", async () => {
    renderPage();
    await screen.findByTestId("flow-folder-mia");

    fireEvent.click(deleteButton("my_flow"));
    let dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("Delete workflow")).toBeInTheDocument();
    expect(within(dialog).getByRole("list", { name: "Workflows to delete" })).toHaveTextContent(
      "my_flow",
    );
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(mocks.deleteFlow).not.toHaveBeenCalled();

    const listCalls = mocks.listFlows.mock.calls.length;
    fireEvent.click(deleteButton("my_flow"));
    dialog = await screen.findByRole("dialog");
    fireEvent.click(within(dialog).getByRole("button", { name: "Delete" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(mocks.deleteFlow).toHaveBeenCalledTimes(1);
    expect(mocks.deleteFlow).toHaveBeenCalledWith("my_flow");
    expect(mocks.toastSuccess).toHaveBeenCalledWith("Deleted my_flow");
    // The list is refetched and no longer shows the deleted flow.
    await waitFor(() => expect(mocks.listFlows.mock.calls.length).toBeGreaterThan(listCalls));
    await waitFor(() => expect(screen.queryAllByRole("link", { name: "my_flow" })).toHaveLength(0));
  });

  it("deletes the selected workflows one at a time and keeps failures selected for retry", async () => {
    mocks.deleteFlow.mockImplementation(async (name: string) => {
      if (name === "zoe_flow") {
        throw { response: { data: { detail: "Flow 'zoe_flow' not found" } } };
      }
      mocks.flows = mocks.flows.filter((item) => item.name !== name);
      return { data: { message: "ok" } };
    });
    renderPage();
    await screen.findByTestId("flow-folder-mia");

    fireEvent.click(selectBox("my_flow"));
    fireEvent.click(selectBox("zoe_flow"));
    fireEvent.click(screen.getByRole("button", { name: "Delete selected" }));

    const dialog = await screen.findByRole("dialog");
    const targets = within(dialog).getByRole("list", { name: "Workflows to delete" });
    expect(
      within(targets)
        .getAllByRole("listitem")
        .map((item) => item.textContent),
    ).toEqual(["zoe_flow", "my_flow"]);
    fireEvent.click(within(dialog).getByRole("button", { name: "Delete 2 workflows" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Could not delete 1 workflow");
    expect(alert).toHaveTextContent("zoe_flow: Flow 'zoe_flow' not found");
    expect(mocks.deleteFlow.mock.calls.map(([name]) => name)).toEqual(["zoe_flow", "my_flow"]);
    expect(mocks.toastSuccess).toHaveBeenCalledWith("Deleted 1 workflow");
    expect(mocks.toastError).toHaveBeenCalledWith("Failed to delete 1 of 2 workflows");

    await waitFor(() => expect(screen.queryAllByRole("link", { name: "my_flow" })).toHaveLength(0));
    expect(screen.getByText("1 selected")).toBeInTheDocument();
    expect(selectBox("zoe_flow")).toBeChecked();

    // Retry confirms only the failed flow.
    fireEvent.click(within(alert).getByRole("button", { name: "Retry" }));
    const retry = await screen.findByRole("dialog");
    expect(within(retry).getByRole("list", { name: "Workflows to delete" })).toHaveTextContent(
      /^zoe_flow$/,
    );
  });

  it("disables every delete control while a deletion is pending", async () => {
    let finish: () => void = () => undefined;
    mocks.deleteFlow.mockImplementation(
      (name: string) =>
        new Promise((resolve) => {
          finish = () => {
            mocks.flows = mocks.flows.filter((item) => item.name !== name);
            resolve({ data: { message: "ok" } });
          };
        }),
    );
    renderPage();
    await screen.findByTestId("flow-folder-mia");

    fireEvent.click(deleteButton("my_flow"));
    const dialog = await screen.findByRole("dialog");
    const confirm = within(dialog).getByRole("button", { name: "Delete" });
    fireEvent.click(confirm);

    await waitFor(() => expect(confirm).toBeDisabled());
    fireEvent.click(confirm);
    expect(mocks.deleteFlow).toHaveBeenCalledTimes(1);
    expect(within(dialog).getByRole("button", { name: "Cancel" })).toBeDisabled();
    // The modal hides the page from the accessibility tree, so query it with hidden: true.
    expect(
      first(screen.getAllByRole("checkbox", { name: "Select workflow zoe_flow", hidden: true })),
    ).toBeDisabled();
    expect(
      first(screen.getAllByRole("button", { name: "Delete workflow zoe_flow", hidden: true })),
    ).toBeDisabled();
    // Escape does not close the dialog mid-request.
    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    finish();
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(deleteButton("zoe_flow")).toBeEnabled();
  });
});

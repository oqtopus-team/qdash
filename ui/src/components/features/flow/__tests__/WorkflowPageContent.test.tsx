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

function folderBox(creator: string, hidden = false) {
  return screen.getByRole("checkbox", {
    name: `Select all workflows by ${creator}`,
    hidden,
  }) as HTMLInputElement;
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
    expect(screen.queryByRole("checkbox", { name: /^Select all workflows by/ })).toBeNull();
    expect(screen.queryByRole("button", { name: /Delete/ })).toBeNull();
  });

  it("selects one creator's workflows, nested and closed folders included, and clears them", async () => {
    mocks.flows = [...mocks.flows, flow("zoe_nested", "zoe", "lab/t1")];
    renderPage();
    await screen.findByTestId("flow-folder-mia");
    // There is no page-wide select all; each creator folder has its own.
    expect(screen.queryByRole("checkbox", { name: /^Select all \d/ })).toBeNull();
    expect(screen.queryByText(/every creator/i)).toBeNull();
    const zoeFolder = screen.getByTestId("flow-folder-zoe");
    const mia = folderBox("mia");
    const zoe = folderBox("zoe");
    const deleteSelected = screen.getByRole("button", { name: "Delete selected" });
    expect(screen.getByText("0 selected")).toBeInTheDocument();
    expect(deleteSelected).toBeDisabled();

    // Zoe's folder is closed; selecting it neither opens it nor touches Mia's flows.
    expect(zoeFolder).not.toHaveAttribute("open");
    fireEvent.click(zoe);
    expect(zoeFolder).not.toHaveAttribute("open");
    expect(zoe).toBeChecked();
    expect(screen.getByText("2 selected")).toBeInTheDocument();
    expect(selectBox("zoe_flow")).toBeChecked();
    expect(selectBox("zoe_nested")).toBeChecked();
    expect(selectBox("my_flow")).not.toBeChecked();
    expect(selectBox("daily_flow")).not.toBeChecked();
    expect(mia).not.toBeChecked();
    expect(mia.indeterminate).toBe(false);
    expect(deleteSelected).toBeEnabled();

    // Several creators can be selected together.
    fireEvent.click(mia);
    expect(screen.getByText("4 selected")).toBeInTheDocument();
    expect(selectBox("daily_flow")).toBeChecked();

    // Deselecting Mia leaves Zoe's selection alone.
    fireEvent.click(mia);
    expect(screen.getByText("2 selected")).toBeInTheDocument();
    expect(zoe).toBeChecked();

    fireEvent.click(screen.getByRole("button", { name: "Clear" }));
    expect(screen.getByText("0 selected")).toBeInTheDocument();
    expect(zoe).not.toBeChecked();
    expect(selectBox("zoe_flow")).not.toBeChecked();
  });

  it("shows a creator folder as mixed while only some of its workflows are selected", async () => {
    renderPage();
    await screen.findByTestId("flow-folder-mia");
    const mia = folderBox("mia");

    fireEvent.click(selectBox("daily_flow"));
    expect(mia.indeterminate).toBe(true);
    expect(mia).not.toBeChecked();
    expect(folderBox("zoe").indeterminate).toBe(false);

    // A mixed folder selects the rest of its workflows.
    fireEvent.click(mia);
    expect(mia.indeterminate).toBe(false);
    expect(mia).toBeChecked();
    expect(selectBox("my_flow")).toBeChecked();
    expect(screen.getByText("2 selected")).toBeInTheDocument();

    // Deselecting one workflow by hand makes the folder mixed again.
    fireEvent.click(selectBox("my_flow"));
    expect(mia.indeterminate).toBe(true);

    // The folder checkbox is not inside the disclosure toggle or a link.
    expect(mia.closest("summary")).toBeNull();
    expect(mia.closest("a")).toBeNull();
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
    expect(folderBox("zoe", true)).toBeDisabled();
    expect(folderBox("mia", true)).toBeDisabled();
    // Escape does not close the dialog mid-request.
    fireEvent.keyDown(dialog, { key: "Escape" });
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    finish();
    await waitFor(() => expect(screen.queryByRole("dialog")).toBeNull());
    expect(deleteButton("zoe_flow")).toBeEnabled();
    expect(folderBox("zoe")).toBeEnabled();
  });
});

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  PROJECT_STORAGE_KEY,
  deferred,
  storeJourney,
  storedJourney,
} from "@/components/features/first-calibration/__tests__/journeyTestUtils";
import { WorkflowEditorPageContent } from "@/components/features/flow/WorkflowEditorPageContent";
import { deleteFlow, saveFlow } from "@/client/flow/flow";

const mocks = vi.hoisted(() => ({
  executeFlow: vi.fn(),
  toastSuccess: vi.fn(),
  toastError: vi.fn(),
  projectId: "project-1",
  push: vi.fn(),
  disabledReason: null as string | null,
  // Saved source per workflow, when a test changes it from the default.
  flowCode: {} as Record<string, string>,
  // Workflows whose source fails to load.
  failingFlows: new Set<string>(),
  getFlow: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mocks.push, back: vi.fn(), replace: vi.fn() }),
  useParams: () => ({ name: "first_calibration" }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("next/dynamic", () => ({
  default: () =>
    function MockEditor({
      value,
      onChange,
      options,
    }: {
      value?: string;
      onChange?: (value?: string) => void;
      options?: { readOnly?: boolean };
    }) {
      return (
        <textarea
          data-testid="editor"
          aria-label="Code"
          value={value ?? ""}
          readOnly={options?.readOnly}
          onChange={(event) => onChange?.(event.target.value)}
        />
      );
    },
}));

vi.mock("react-resizable-panels", () => ({
  Panel: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  Group: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  Separator: () => <div />,
}));

vi.mock("@/components/features/flow/FlowExplorer", () => ({
  FlowExplorer: ({
    currentName,
    onOpen,
  }: {
    currentName: string;
    onOpen: (name: string) => void;
  }) => (
    <div data-testid="explorer" data-current={currentName}>
      {["first_calibration", "other_flow", "third_flow"].map((flowName) => (
        <button key={flowName} type="button" onClick={() => onOpen(flowName)}>
          Explorer {flowName}
        </button>
      ))}
    </div>
  ),
}));
vi.mock("@/components/features/flow/FlowSchedulePanel", () => ({
  FlowSchedulePanel: () => null,
}));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ username: "alice" }),
}));

vi.mock("@/contexts/ProjectContext", () => ({
  useProject: () => ({ projectId: mocks.projectId, canEdit: true }),
}));

vi.mock("@/contexts/ChatDockContext", () => ({
  useChatDock: () => ({ registerPage: () => () => undefined }),
}));

vi.mock("@/components/ui/Toast", () => ({
  useToast: () => ({ success: mocks.toastSuccess, error: mocks.toastError }),
}));

vi.mock("@/hooks/useExecutionAvailability", () => ({
  useExecutionAvailability: () => ({ disabledReason: mocks.disabledReason }),
}));

vi.mock("@/client/auth/auth", () => ({
  useGetCurrentUser: () => ({ data: { data: { username: "alice" } } }),
}));

vi.mock("@/client/chip/chip", () => ({
  useListChips: () => ({
    data: { data: { chips: [{ chip_id: "chip-a", size: 64 }] } },
  }),
}));

vi.mock("@/client/execution/execution", () => ({
  getGetExecutionLockStatusQueryKey: () => ["/executions/lock-status"],
  useCancelExecution: () => ({ mutate: vi.fn(), isPending: false }),
  useGetExecution: () => ({ data: undefined }),
  useGetExecutionLockStatus: () => ({ data: undefined }),
}));

// Each workflow has its own source and chip, so a pane showing or saving the wrong one shows.
const FLOW_CHIPS: Record<string, string> = {
  first_calibration: "chip-a",
  other_flow: "chip-b",
  third_flow: "chip-c",
};

mocks.getFlow.mockImplementation((flowName: string) =>
  mocks.failingFlows.has(flowName)
    ? Promise.reject(new Error("source file missing"))
    : Promise.resolve({
        data: {
          name: flowName,
          description: "",
          code:
            mocks.flowCode[flowName] ??
            (flowName === "first_calibration" ? "from prefect import flow\n" : `# ${flowName}\n`),
          flow_function_name: flowName,
          chip_id: FLOW_CHIPS[flowName] ?? "chip-a",
          default_parameters: { username: "alice", chip_id: FLOW_CHIPS[flowName] ?? "chip-a" },
          default_run_parameters: {},
          tags: [],
          folder: "",
        },
      }),
);

vi.mock("@/client/flow/flow", () => ({
  getFlow: (flowName: string) => mocks.getFlow(flowName),
  getListFlowsQueryKey: () => ["/flows"],
  saveFlow: vi.fn(),
  deleteFlow: vi.fn(),
  executeFlow: mocks.executeFlow,
  useListFlows: () => ({ data: { data: { flows: [] } } }),
  listFlowSchedules: () => Promise.resolve({ data: { schedules: [] } }),
}));

function renderEditor() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const page = () => (
    <QueryClientProvider client={client}>
      <WorkflowEditorPageContent />
    </QueryClientProvider>
  );
  const view = render(page());
  return { client, rerender: () => view.rerender(page()) };
}

async function confirmExecute() {
  const header = await screen.findByTitle("Execute Flow");
  fireEvent.click(header);
  const dialog = screen.getByRole("heading", { name: "Execute Flow" }).closest("div.bg-base-100");
  const scope = dialog instanceof HTMLElement ? within(dialog) : screen;
  const confirm = scope
    .getAllByRole("button", { name: "Execute" })
    .find(
      (button) =>
        button.getAttribute("data-coachmark") === "flow-execute-confirm" && button !== header,
    );
  if (!confirm) throw new Error("Execute confirmation button not found");
  await act(async () => {
    fireEvent.click(confirm);
  });
}

describe("WorkflowEditorPageContent run callbacks", () => {
  beforeEach(() => {
    mocks.projectId = "project-1";
    mocks.disabledReason = null;
    window.localStorage.setItem(PROJECT_STORAGE_KEY, "project-1");
    const atRun = { chipId: "chip-a", flowName: "first_calibration" };
    storeJourney("project-1", atRun);
    storeJourney("project-2", atRun);
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    window.localStorage.clear();
  });

  it("reports a confirmed run to the guide of the same project", async () => {
    mocks.executeFlow.mockResolvedValue({
      data: { execution_id: "20261105-001", flow_run_id: "run-1" },
    });
    renderEditor();

    await confirmExecute();

    await waitFor(() => expect(storedJourney("project-1").executionId).toBe("20261105-001"));
    expect(mocks.executeFlow).toHaveBeenCalledWith(
      "first_calibration",
      expect.objectContaining({
        parameters: expect.objectContaining({ chip_id: "chip-a" }),
      }),
    );
    expect(storedJourney("project-1").executionId).toBe("20261105-001");
    expect(mocks.toastSuccess).toHaveBeenCalled();
    // The guide's run opens on its execution page, once, without a banner click.
    expect(mocks.push).toHaveBeenCalledTimes(1);
    expect(mocks.push).toHaveBeenCalledWith("/execution/chip-a/20261105-001");
  });

  it("marks Execute ready for the guide only while it can start a run", async () => {
    mocks.disabledReason = "Checking hardware availability…";
    const view = renderEditor();
    const execute = await screen.findByTitle("Checking hardware availability…");
    expect(execute).toHaveAttribute("data-coachmark", "flow-execute");
    expect(execute).not.toHaveAttribute("data-coachmark-ready");
    expect(execute).toBeDisabled();
    expect(execute).toHaveAccessibleDescription("Checking hardware availability…");
    expect(screen.getByRole("status")).toHaveTextContent("Checking hardware availability…");

    mocks.disabledReason = null;
    view.rerender();
    expect(await screen.findByTitle("Execute Flow")).toHaveAttribute(
      "data-coachmark-ready",
      "true",
    );
    // Mounting and re-rendering never start a run by themselves.
    expect(mocks.executeFlow).not.toHaveBeenCalled();
  });

  it("stays on the editor when starting the run fails", async () => {
    mocks.executeFlow.mockRejectedValue(new Error("deployment missing"));
    renderEditor();

    await confirmExecute();

    expect(await screen.findByText(/Failed to execute flow/)).toBeInTheDocument();
    expect(storedJourney("project-1").executionId).toBeNull();
    expect(mocks.push).not.toHaveBeenCalled();
  });

  it("records but does not navigate when the guide was paused while the run started", async () => {
    const pending = deferred<{
      data: { execution_id: string; flow_run_id: string };
    }>();
    mocks.executeFlow.mockReturnValue(pending.promise);
    renderEditor();

    await confirmExecute();
    storeJourney("project-1", {
      chipId: "chip-a",
      flowName: "first_calibration",
      status: "paused",
    });
    await act(async () => {
      pending.resolve({
        data: { execution_id: "20261105-002", flow_run_id: "run-2" },
      });
      await pending.promise;
    });

    expect(mocks.toastSuccess).toHaveBeenCalled();
    expect(mocks.push).not.toHaveBeenCalled();
  });

  it("keeps a run outside the guide on the editor", async () => {
    // The guide follows another flow; this run is ordinary editor work.
    storeJourney("project-1", { chipId: "chip-a", flowName: "other_flow" });
    mocks.executeFlow.mockResolvedValue({
      data: { execution_id: "20261105-003", flow_run_id: "run-3" },
    });
    renderEditor();

    await confirmExecute();

    await waitFor(() => expect(mocks.toastSuccess).toHaveBeenCalled());
    expect(storedJourney("project-1").executionId).toBeNull();
    expect(mocks.push).not.toHaveBeenCalled();
  });

  it("ignores a run that answers after the user switched project", async () => {
    const pending = deferred<{
      data: { execution_id: string; flow_run_id: string };
    }>();
    mocks.executeFlow.mockReturnValue(pending.promise);
    const view = renderEditor();

    await confirmExecute();
    expect(mocks.executeFlow).toHaveBeenCalledTimes(1);

    // Same flow name, chip and execution id in the other project: only the context differs.
    mocks.projectId = "project-2";
    window.localStorage.setItem(PROJECT_STORAGE_KEY, "project-2");
    view.rerender();
    await act(async () => {
      pending.resolve({
        data: { execution_id: "20261105-001", flow_run_id: "run-1" },
      });
      await pending.promise;
    });

    expect(storedJourney("project-1").executionId).toBeNull();
    expect(storedJourney("project-2").executionId).toBeNull();
    expect(mocks.toastSuccess).not.toHaveBeenCalled();
  });
});

describe("WorkflowEditorPageContent execution help", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    window.localStorage.clear();
  });

  it("opens and closes the help over the editor without saving or running the flow", async () => {
    renderEditor();
    const editor = await screen.findByTestId("editor");
    // The header button and the mobile action menu both open the same dialog.
    const triggers = screen.getAllByRole("button", { name: "Execution help" });
    expect(triggers).toHaveLength(2);

    triggers[0].focus();
    fireEvent.click(triggers[0]);
    const dialog = screen.getByRole("dialog", { name: "Execution help" });
    fireEvent.click(within(dialog).getByRole("tab", { name: "2Q CR groups" }));
    expect(within(dialog).getByRole("tabpanel")).toHaveTextContent(/max_parallel_ops/);

    fireEvent.keyDown(dialog, { key: "Escape" });

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    await waitFor(() => expect(triggers[0]).toHaveFocus());
    // The same editor instance stays mounted, so an unsaved draft survives.
    expect(screen.getByTestId("editor")).toBe(editor);
    expect(saveFlow).not.toHaveBeenCalled();
    expect(mocks.executeFlow).not.toHaveBeenCalled();
    expect(mocks.push).not.toHaveBeenCalled();
  });

  it("opens from the mobile action menu", async () => {
    renderEditor();
    await screen.findByTestId("editor");

    fireEvent.click(screen.getAllByRole("button", { name: "Execution help" })[1]);

    expect(screen.getByRole("dialog", { name: "Execution help" })).toBeInTheDocument();
  });
});

describe("WorkflowEditorPageContent split editor", () => {
  beforeEach(() => {
    mocks.projectId = "project-1";
    mocks.disabledReason = null;
    // A save answers only in the project it was submitted in.
    window.localStorage.setItem(PROJECT_STORAGE_KEY, "project-1");
    vi.mocked(saveFlow).mockResolvedValue({ data: {} } as Awaited<ReturnType<typeof saveFlow>>);
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    window.localStorage.clear();
    mocks.flowCode = {};
    mocks.failingFlows.clear();
  });

  const pane = (side: "Left" | "Right") => screen.getByRole("region", { name: new RegExp(side) });

  async function openSplitWith(flowName: string) {
    renderEditor();
    await screen.findByTestId("editor");
    fireEvent.click(screen.getByRole("button", { name: "Open split editor" }));
    // The new right pane is active and waits for a workflow from the Explorer.
    expect(pane("Right")).toHaveTextContent("Select a workflow in the Explorer");
    expect(screen.getByText(/Opens in the/)).toHaveTextContent("Opens in the right pane");
    fireEvent.click(screen.getByRole("button", { name: `Explorer ${flowName}` }));
    await waitFor(() =>
      expect(within(pane("Right")).getByLabelText("Code")).toHaveValue(`# ${flowName}\n`),
    );
  }

  it("opens a different workflow in each pane and saves the right pane's workflow", async () => {
    await openSplitWith("other_flow");

    expect(within(pane("Left")).getByLabelText("Code")).toHaveValue("from prefect import flow\n");
    expect(screen.getByRole("region", { name: "Left editor: first_calibration.py" })).toBeVisible();
    expect(screen.getByRole("region", { name: "Right editor: other_flow.py" })).toBeVisible();
    expect(screen.getByTestId("explorer")).toHaveAttribute("data-current", "other_flow");

    fireEvent.click(screen.getByTitle("Click to edit"));
    fireEvent.change(within(pane("Right")).getByLabelText("Code"), {
      target: { value: "# other_flow edited\n" },
    });
    // Only the right pane's workflow is modified.
    expect(within(pane("Right")).getByTitle("Unsaved changes")).toBeInTheDocument();
    expect(within(pane("Left")).queryByTitle("Unsaved changes")).not.toBeInTheDocument();

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Save" }));
    });

    expect(saveFlow).toHaveBeenCalledTimes(1);
    expect(saveFlow).toHaveBeenCalledWith(
      expect.objectContaining({
        name: "other_flow",
        code: "# other_flow edited\n",
        chip_id: "chip-b",
      }),
    );
    expect(within(pane("Left")).getByLabelText("Code")).toHaveValue("from prefect import flow\n");
  });

  it("saves and runs the workflow of the pane the user activated", async () => {
    mocks.executeFlow.mockResolvedValue({
      data: { execution_id: "20261113-001", flow_run_id: "run-1" },
    });
    await openSplitWith("other_flow");

    // Activate the left pane: actions and the Explorer now follow its workflow.
    fireEvent.click(within(pane("Left")).getByRole("button", { name: /first_calibration\.py/ }));
    expect(
      within(pane("Left")).getByRole("button", { name: /first_calibration\.py/ }),
    ).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByTestId("explorer")).toHaveAttribute("data-current", "first_calibration");

    fireEvent.click(screen.getByTitle("Click to edit"));
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Save" }));
    });
    expect(saveFlow).toHaveBeenCalledWith(
      expect.objectContaining({ name: "first_calibration", chip_id: "chip-a" }),
    );

    // Focusing the right editor makes it active, and Execute runs that workflow.
    fireEvent.focus(within(pane("Right")).getByLabelText("Code"));
    await confirmExecute();
    expect(mocks.executeFlow).toHaveBeenCalledTimes(1);
    expect(mocks.executeFlow).toHaveBeenCalledWith(
      "other_flow",
      expect.objectContaining({
        parameters: expect.objectContaining({ chip_id: "chip-b" }),
      }),
    );
  });

  it("asks before replacing or closing a right pane with unsaved changes", async () => {
    await openSplitWith("other_flow");
    fireEvent.click(screen.getByTitle("Click to edit"));
    fireEvent.change(within(pane("Right")).getByLabelText("Code"), {
      target: { value: "# draft\n" },
    });

    // Opening another workflow in the dirty pane waits for confirmation; Cancel keeps the draft.
    fireEvent.click(screen.getByRole("button", { name: "Explorer third_flow" }));
    const dialog = screen.getByRole("dialog", { name: "Discard unsaved changes?" });
    expect(dialog).toHaveTextContent("other_flow.py");
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    expect(within(pane("Right")).getByLabelText("Code")).toHaveValue("# draft\n");

    // Closing the split waits too.
    fireEvent.click(screen.getByRole("button", { name: "Close split editor" }));
    fireEvent.click(
      within(screen.getByRole("dialog", { name: "Discard unsaved changes?" })).getByRole("button", {
        name: "Cancel",
      }),
    );
    expect(within(pane("Right")).getByLabelText("Code")).toHaveValue("# draft\n");

    // Confirming replaces the right pane's workflow; the left pane is untouched.
    fireEvent.click(screen.getByRole("button", { name: "Explorer third_flow" }));
    fireEvent.click(screen.getByRole("button", { name: "Discard changes" }));
    await waitFor(() =>
      expect(within(pane("Right")).getByLabelText("Code")).toHaveValue("# third_flow\n"),
    );
    expect(screen.getByRole("region", { name: "Right editor: third_flow.py" })).toBeVisible();
    expect(within(pane("Left")).getByLabelText("Code")).toHaveValue("from prefect import flow\n");
    expect(saveFlow).not.toHaveBeenCalled();
  });

  it("does not open one workflow in both panes", async () => {
    await openSplitWith("other_flow");

    // Picking the left pane's workflow while the right pane is active focuses the left pane.
    fireEvent.click(screen.getByRole("button", { name: "Explorer first_calibration" }));

    expect(screen.getByRole("region", { name: "Right editor: other_flow.py" })).toBeVisible();
    expect(screen.getByTestId("explorer")).toHaveAttribute("data-current", "first_calibration");
    expect(mocks.push).not.toHaveBeenCalled();
  });

  it("keeps the right pane's workflow when the left pane opens another", async () => {
    await openSplitWith("other_flow");
    fireEvent.click(within(pane("Left")).getByRole("button", { name: /first_calibration\.py/ }));

    fireEvent.click(screen.getByRole("button", { name: "Explorer third_flow" }));

    expect(mocks.push).toHaveBeenCalledWith("/workflow/third_flow?split=other_flow");
  });

  it("asks before the single editor opens another workflow over unsaved changes", async () => {
    renderEditor();
    await screen.findByTestId("editor");
    fireEvent.click(screen.getByTitle("Click to edit"));
    fireEvent.change(screen.getByLabelText("Code"), { target: { value: "# changed\n" } });

    fireEvent.click(screen.getByRole("button", { name: "Explorer other_flow" }));
    expect(mocks.push).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Discard changes" }));

    expect(mocks.push).toHaveBeenCalledWith("/workflow/other_flow");
  });

  it("keeps edits made while a save is pending and refreshes both workflow lists", async () => {
    const pending = deferred<Awaited<ReturnType<typeof saveFlow>>>();
    vi.mocked(saveFlow).mockReturnValue(pending.promise as ReturnType<typeof saveFlow>);
    const { client } = renderEditor();
    const invalidate = vi.spyOn(client, "invalidateQueries");
    await screen.findByTestId("editor");
    fireEvent.click(screen.getByTitle("Click to edit"));
    fireEvent.change(screen.getByLabelText("Code"), { target: { value: "# v1\n" } });

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Save" }));
    });
    expect(saveFlow).toHaveBeenCalledWith(expect.objectContaining({ code: "# v1\n" }));

    // The user keeps typing while the save is in flight.
    fireEvent.change(screen.getByLabelText("Code"), { target: { value: "# v2\n" } });
    mocks.flowCode.first_calibration = "# v1\n";
    const loads = mocks.getFlow.mock.calls.length;
    await act(async () => {
      pending.resolve({ data: {} } as Awaited<ReturnType<typeof saveFlow>>);
      await pending.promise;
    });

    // The save refetches the workflow, which answers with the submitted source.
    await waitFor(() => expect(mocks.getFlow.mock.calls.length).toBeGreaterThan(loads));
    await waitFor(() =>
      expect(client.getQueryState(["flow", "first_calibration"])?.fetchStatus).toBe("idle"),
    );
    expect(screen.getByLabelText("Code")).toHaveValue("# v2\n");
    expect(screen.getByTitle("Unsaved changes")).toBeInTheDocument();
    // The submitted source is the new baseline: returning to it leaves nothing unsaved.
    fireEvent.change(screen.getByLabelText("Code"), { target: { value: "# v1\n" } });
    expect(screen.queryByTitle("Unsaved changes")).not.toBeInTheDocument();

    // The Workflow page's list and the editor's Explorer list are both refreshed.
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["flows"] });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: ["/flows"] });
  });

  it("asks before deleting a workflow that failed to load over a right-pane draft", async () => {
    vi.mocked(deleteFlow).mockResolvedValue({} as Awaited<ReturnType<typeof deleteFlow>>);
    const { client } = renderEditor();
    await screen.findByTestId("editor");
    fireEvent.click(screen.getByRole("button", { name: "Open split editor" }));
    fireEvent.click(screen.getByRole("button", { name: "Explorer other_flow" }));
    await waitFor(() =>
      expect(within(pane("Right")).getByLabelText("Code")).toHaveValue("# other_flow\n"),
    );
    fireEvent.click(screen.getByTitle("Click to edit"));
    fireEvent.change(within(pane("Right")).getByLabelText("Code"), {
      target: { value: "# draft\n" },
    });

    // The left pane's source can no longer be loaded.
    mocks.failingFlows.add("first_calibration");
    await act(async () => {
      await client.invalidateQueries({ queryKey: ["flow", "first_calibration"] });
    });
    expect(await screen.findByText("Failed to load flow")).toBeInTheDocument();

    const deleteMetadata = async () => {
      fireEvent.click(screen.getByRole("button", { name: "Delete Flow Metadata" }));
      fireEvent.click(
        within(screen.getByRole("dialog", { name: "Delete Flow" })).getByRole("button", {
          name: "Delete",
        }),
      );
      return screen.findByRole("dialog", { name: "Discard unsaved changes?" });
    };

    // Cancel keeps the metadata and the right pane's draft.
    const dialog = await deleteMetadata();
    expect(dialog).toHaveTextContent("other_flow.py");
    fireEvent.click(within(dialog).getByRole("button", { name: "Cancel" }));
    await waitFor(() =>
      expect(
        screen.queryByRole("dialog", { name: "Discard unsaved changes?" }),
      ).not.toBeInTheDocument(),
    );
    expect(deleteFlow).not.toHaveBeenCalled();

    // Confirming discards the draft and deletes the left pane's workflow.
    const again = await deleteMetadata();
    await act(async () => {
      fireEvent.click(within(again).getByRole("button", { name: "Discard changes" }));
    });
    expect(deleteFlow).toHaveBeenCalledTimes(1);
    expect(deleteFlow).toHaveBeenCalledWith("first_calibration");
    await waitFor(() => expect(mocks.push).toHaveBeenCalledWith("/workflow"));
  });
});

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { useEffect, type ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  PROJECT_STORAGE_KEY,
  deferred,
  storeJourney,
  storedJourney,
} from "@/components/features/first-calibration/__tests__/journeyTestUtils";
import { WorkflowEditorPageContent } from "@/components/features/flow/WorkflowEditorPageContent";

const mocks = vi.hoisted(() => ({
  monaco: {
    KeyMod: { CtrlCmd: 2048, Alt: 512 },
    KeyCode: { KeyS: 49, KeyZ: 56 },
    editor: { remeasureFonts: () => undefined },
  },
  executeFlow: vi.fn(),
  saveFlow: vi.fn(),
  editorCommands: new Map<number, () => void>(),
  editorChange: null as ((value: string) => void) | null,
  toastSuccess: vi.fn(),
  toastError: vi.fn(),
  projectId: "project-1",
  push: vi.fn(),
  disabledReason: null as string | null,
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mocks.push, back: vi.fn(), replace: vi.fn() }),
  useParams: () => ({ name: "first_calibration" }),
  useSearchParams: () => new URLSearchParams(),
}));

vi.mock("next/dynamic", () => ({
  default: () =>
    /** Monaco stand-in that registers the editor commands, such as Cmd/Ctrl+S, on mount. */
    function MockEditor({
      onMount,
      onChange,
    }: {
      onMount?: (editor: unknown, monaco: unknown) => void;
      onChange?: (value: string) => void;
    }) {
      mocks.editorChange = onChange ?? null;
      useEffect(() => {
        onMount?.(
          {
            onDidChangeCursorPosition: () => undefined,
            onDidChangeCursorSelection: () => undefined,
            updateOptions: () => undefined,
            addCommand: (keybinding: number, handler: () => void) =>
              mocks.editorCommands.set(keybinding, handler),
          },
          mocks.monaco,
        );
      }, [onMount]);
      return <div data-testid="editor" />;
    },
}));

vi.mock("react-resizable-panels", () => ({
  Panel: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  Group: ({ children }: { children?: ReactNode }) => <div>{children}</div>,
  Separator: () => <div />,
}));

vi.mock("@/components/features/flow/FlowExplorer", () => ({
  FlowExplorer: () => null,
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

vi.mock("@/client/flow/flow", () => ({
  getFlow: () =>
    Promise.resolve({
      data: {
        name: "first_calibration",
        description: "",
        code: "from prefect import flow\n",
        flow_function_name: "first_calibration",
        chip_id: "chip-a",
        default_parameters: { username: "alice", chip_id: "chip-a" },
        default_run_parameters: {},
        tags: [],
        folder: "",
      },
    }),
  saveFlow: mocks.saveFlow,
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
  return { rerender: () => view.rerender(page()) };
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

/** Presses Cmd/Ctrl+S in the Monaco editor. */
async function pressSaveShortcut() {
  const save = mocks.editorCommands.get(mocks.monaco.KeyMod.CtrlCmd | mocks.monaco.KeyCode.KeyS);
  if (!save) throw new Error("Cmd/Ctrl+S is not registered");
  await act(async () => {
    save();
  });
}

/** Unlocks the editor once the flow has loaded. */
async function unlockEditor() {
  fireEvent.click(await screen.findByTitle("Click to edit"));
}

/** Opens the Properties side panel from the activity bar button, which follows the header button. */
function openPropertiesPanel() {
  fireEvent.click(screen.getAllByRole("button", { name: "Properties" })[1]);
}

/** Types new code into the Monaco editor. */
function typeCode(value: string) {
  act(() => mocks.editorChange?.(value));
}

/** Whether leaving the page now asks the browser to warn about unsaved changes. */
function warnsBeforeUnload() {
  const event = new Event("beforeunload", { cancelable: true });
  window.dispatchEvent(event);
  return event.defaultPrevented;
}

describe("WorkflowEditorPageContent properties", () => {
  beforeEach(() => {
    mocks.projectId = "project-1";
    mocks.disabledReason = null;
    mocks.editorCommands.clear();
    window.localStorage.setItem(PROJECT_STORAGE_KEY, "project-1");
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    window.localStorage.clear();
  });

  it("saves the properties and the code through Cmd/Ctrl+S", async () => {
    mocks.saveFlow.mockResolvedValue({ data: { name: "first_calibration" } });
    renderEditor();
    await unlockEditor();
    expect(warnsBeforeUnload()).toBe(false);

    openPropertiesPanel();
    fireEvent.change(screen.getByLabelText("Description"), {
      target: { value: "  Daily T1  " },
    });
    fireEvent.change(screen.getByLabelText("Tags"), { target: { value: " t1, , daily " } });
    fireEvent.change(screen.getByLabelText("Default Interval (ns)"), {
      target: { value: " 150 * 1024 " },
    });
    expect(screen.queryByTitle("Unsaved changes")).toBeNull();
    expect(warnsBeforeUnload()).toBe(false);

    typeCode("from prefect import flow\n\n# edited\n");
    expect(screen.getByTitle("Unsaved changes")).toBeInTheDocument();
    expect(warnsBeforeUnload()).toBe(true);

    await pressSaveShortcut();

    await waitFor(() =>
      expect(mocks.toastSuccess).toHaveBeenCalledWith("Flow saved successfully!"),
    );
    expect(mocks.saveFlow).toHaveBeenCalledWith({
      name: "first_calibration",
      description: "Daily T1",
      code: "from prefect import flow\n\n# edited\n",
      flow_function_name: "first_calibration",
      chip_id: "chip-a",
      tags: ["t1", "daily"],
      folder: "",
      default_parameters: { username: "alice", chip_id: "chip-a" },
      default_run_parameters: {
        interval: { value: "150 * 1024", value_type: "int", unit: "ns" },
      },
    });
    await waitFor(() => expect(screen.queryByTitle("Unsaved changes")).toBeNull());
    expect(warnsBeforeUnload()).toBe(false);
    expect(mocks.toastError).not.toHaveBeenCalled();
  });

  it("does not save through Cmd/Ctrl+S while the editor is locked", async () => {
    renderEditor();
    await screen.findByTitle("Click to edit");

    await pressSaveShortcut();

    expect(mocks.saveFlow).not.toHaveBeenCalled();
  });

  it("shows and focuses a hidden invalid username when saving by shortcut", async () => {
    renderEditor();
    await unlockEditor();
    openPropertiesPanel();
    fireEvent.change(screen.getByLabelText("Username *"), { target: { value: "   " } });
    fireEvent.click(screen.getByRole("button", { name: "Explorer" }));
    expect(screen.queryByLabelText("Username *")).toBeNull();

    await pressSaveShortcut();

    const username = await screen.findByLabelText("Username *");
    await waitFor(() => expect(document.activeElement).toBe(username));
    expect(username).toHaveAttribute("aria-invalid", "true");
    const error = document.getElementById(username.getAttribute("aria-describedby") ?? "");
    expect(error).toHaveTextContent("Please enter a username");
    expect(mocks.saveFlow).not.toHaveBeenCalled();
    expect(mocks.toastError).not.toHaveBeenCalled();

    mocks.saveFlow.mockResolvedValue({ data: { name: "first_calibration" } });
    fireEvent.change(username, { target: { value: " bob " } });
    await waitFor(() => expect(username).not.toHaveAttribute("aria-invalid", "true"));
    await pressSaveShortcut();
    await waitFor(() =>
      expect(mocks.saveFlow).toHaveBeenCalledWith(
        expect.objectContaining({
          default_parameters: { username: "bob", chip_id: "chip-a" },
        }),
      ),
    );
  });

  it("saves from the command palette and reports an invalid field in the open modal", async () => {
    renderEditor();
    await unlockEditor();
    fireEvent.click(screen.getAllByRole("button", { name: "Properties" })[0]);
    const dialog = await screen.findByRole("dialog", { name: "Properties" });
    fireEvent.change(within(dialog).getByLabelText("Username *"), { target: { value: "" } });

    fireEvent.keyDown(window, { key: "p", ctrlKey: true, shiftKey: true });
    fireEvent.click(await screen.findByRole("option", { name: /Save Flow/ }));

    const username = await within(
      await screen.findByRole("dialog", { name: "Properties" }),
    ).findByLabelText("Username *");
    await waitFor(() => expect(document.activeElement).toBe(username));
    expect(username).toHaveAttribute("aria-invalid", "true");
    expect(screen.getAllByText("Please enter a username").length).toBeGreaterThan(0);
    expect(mocks.saveFlow).not.toHaveBeenCalled();
  });

  it("keeps a failed save as a submission error", async () => {
    mocks.saveFlow.mockRejectedValue(new Error("disk full"));
    renderEditor();
    await unlockEditor();

    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(await screen.findByText("Failed to save flow: disk full")).toBeInTheDocument();
    expect(screen.queryByText("Please enter a username")).toBeNull();
  });
});

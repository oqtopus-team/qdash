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

const mocks = vi.hoisted(() => ({
  executeFlow: vi.fn(),
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
    function MockEditor() {
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
  return { rerender: () => view.rerender(page()) };
}

async function confirmExecute() {
  const header = await screen.findByTitle("Execute Flow");
  fireEvent.click(header);
  const dialog = screen.getByRole("heading", { name: "Execute Flow" }).closest("div.bg-base-100");
  const scope = dialog instanceof HTMLElement ? within(dialog) : screen;
  const confirm = scope
    .getAllByRole("button", { name: "Execute" })
    .find((button) => button.className.includes("btn-success") && button !== header);
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

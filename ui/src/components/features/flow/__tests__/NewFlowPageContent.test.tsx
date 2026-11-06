import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { AxiosError, type AxiosResponse } from "axios";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  PROJECT_STORAGE_KEY,
  deferred,
  storeJourney,
  storedJourney,
} from "@/components/features/first-calibration/__tests__/journeyTestUtils";
import { NewFlowPageContent } from "@/components/features/flow/NewFlowPageContent";

const mocks = vi.hoisted(() => ({
  push: vi.fn(),
  saveFlow: vi.fn(),
  toastSuccess: vi.fn(),
  toastError: vi.fn(),
  projectId: "project-1",
  query: {
    chip_id: "chip-a",
    backend: "fake",
    template: null,
    journey: "first-calibration",
  } as Record<string, string | null>,
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: mocks.push, back: vi.fn() }),
}));

vi.mock("next/dynamic", () => ({
  default: () =>
    function MockEditor({ value }: { value: string }) {
      return <pre data-testid="editor">{value}</pre>;
    },
}));

vi.mock("nuqs", () => ({
  parseAsString: { withDefault: () => ({}) },
  useQueryState: (key: string) => [mocks.query[key] ?? null, vi.fn()],
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

vi.mock("@/client/auth/auth", () => ({
  useGetCurrentUser: () => ({ data: { data: { username: "alice" } } }),
}));

vi.mock("@/client/chip/chip", () => ({
  useListChips: () => ({
    data: { data: { chips: [{ chip_id: "chip-a", size: 64 }] } },
  }),
}));

const FAKE_TEMPLATE_CODE = [
  "FAKE_CALIBRATION_TASKS: list[str] = [",
  '    "FakeBringUp",',
  '    "CheckRabi",',
  "]",
  "MUX_IDS: list[int] = [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]",
  "",
].join("\n");

vi.mock("@/client/flow/flow", () => ({
  saveFlow: mocks.saveFlow,
  getFlowTemplate: () =>
    Promise.resolve({
      data: {
        id: "fake_calibration",
        name: "Fake Backend Calibration",
        description: "",
        code: FAKE_TEMPLATE_CODE,
        function_name: "fake_calibration",
      },
    }),
  listFlowTemplates: () =>
    Promise.resolve({
      data: [
        {
          id: "fake_calibration",
          name: "Fake Backend Calibration",
          description: "",
          category: "fake",
          backend: "fake",
          filename: "fake_backend.py",
          function_name: "fake_calibration",
        },
      ],
    }),
  useListFlows: () => ({ data: { data: { flows: [] } } }),
}));

vi.mock("@/client/task-file/task-file", () => ({
  getTaskFileSettings: () => Promise.resolve({ data: { default_backend: "fake" } }),
  listTaskFileBackends: () => Promise.resolve({ data: { backends: [{ name: "fake" }] } }),
}));

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const page = () => (
    <QueryClientProvider client={client}>
      <NewFlowPageContent />
    </QueryClientProvider>
  );
  const view = render(page());
  return { rerender: () => view.rerender(page()) };
}

function nameInput() {
  return screen.getByLabelText("Flow Name *") as HTMLInputElement;
}

async function save() {
  await waitFor(() => expect(nameInput().value).toBe("first_calibration"));
  fireEvent.click(screen.getByRole("button", { name: /Save Flow/ }));
}

function conflict(name: string) {
  return new AxiosError("Request failed with status code 409", "ERR_BAD_REQUEST", undefined, null, {
    status: 409,
    statusText: "Conflict",
    headers: {},
    config: {},
    data: { detail: `Flow '${name}' already exists. Choose another name.` },
  } as AxiosResponse);
}

describe("NewFlowPageContent", () => {
  beforeEach(() => {
    mocks.projectId = "project-1";
    window.localStorage.setItem(PROJECT_STORAGE_KEY, "project-1");
    storeJourney("project-1", { chipId: "chip-a" });
    storeJourney("project-2", { chipId: "chip-a" });
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    window.localStorage.clear();
  });

  it("creates the flow without overwriting and reports it to the guide", async () => {
    mocks.saveFlow.mockResolvedValue({ data: { name: "first_calibration" } });
    renderPage();

    await save();

    await waitFor(() => expect(mocks.push).toHaveBeenCalledWith("/workflow/first_calibration"));
    expect(mocks.saveFlow).toHaveBeenCalledWith(
      expect.objectContaining({
        name: "first_calibration",
        chip_id: "chip-a",
        create_only: true,
      }),
    );
    expect(storedJourney("project-1").flowName).toBe("first_calibration");
  });

  it("summarizes the tasks and MUX targets of the code for the guide, read only", async () => {
    renderPage();

    const summary = await screen.findByRole("region", {
      name: "What this flow runs",
    });
    expect(summary).toHaveAttribute("data-coachmark-ready", "true");
    expect(summary).toHaveTextContent("1. FakeBringUp");
    expect(summary).toHaveTextContent("2. CheckRabi");
    expect(summary).toHaveTextContent("MUX 0–15 of chip-a");
    // The editor keeps the template's code; the guide never rewrites or saves it.
    expect(screen.getByTestId("editor").textContent).toBe(FAKE_TEMPLATE_CODE);
    expect(mocks.saveFlow).not.toHaveBeenCalled();
  });

  it("shows no guide summary in the ordinary editor", async () => {
    mocks.query.journey = null;
    try {
      renderPage();
      await waitFor(() =>
        expect(screen.getByTestId("editor").textContent).toBe(FAKE_TEMPLATE_CODE),
      );
      expect(screen.queryByRole("region", { name: "What this flow runs" })).toBeNull();
    } finally {
      mocks.query.journey = "first-calibration";
    }
  });

  it("keeps the inputs and asks for another name when the name is taken", async () => {
    mocks.saveFlow.mockRejectedValue(conflict("first_calibration"));
    renderPage();
    // The template sets the description when it loads; type after that.
    await waitFor(() => expect(screen.getByTestId("editor").textContent).toBe(FAKE_TEMPLATE_CODE));
    fireEvent.change(screen.getByPlaceholderText("Describe your flow..."), {
      target: { value: "My first run" },
    });

    await save();

    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toContain("A flow named first_calibration already exists");
    expect(nameInput().value).toBe("first_calibration");
    expect(nameInput()).toHaveAttribute("aria-invalid", "true");
    expect(nameInput().getAttribute("aria-describedby")).toBe(alert.id);
    expect(document.activeElement).toBe(nameInput());
    expect(
      (screen.getByPlaceholderText("Describe your flow...") as HTMLTextAreaElement).value,
    ).toBe("My first run");
    expect(mocks.push).not.toHaveBeenCalled();
    expect(storedJourney("project-1").flowName).toBeNull();

    // Editing the name clears the conflict so the next save starts clean.
    fireEvent.change(nameInput(), { target: { value: "first_calibration_2" } });
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("ignores a save that answers after the user switched project", async () => {
    const pending = deferred<{ data: { name: string } }>();
    mocks.saveFlow.mockReturnValue(pending.promise);
    const view = renderPage();

    await save();
    expect(mocks.saveFlow).toHaveBeenCalledTimes(1);

    mocks.projectId = "project-2";
    window.localStorage.setItem(PROJECT_STORAGE_KEY, "project-2");
    view.rerender();
    await act(async () => {
      pending.resolve({ data: { name: "first_calibration" } });
      await pending.promise;
    });

    expect(mocks.push).not.toHaveBeenCalled();
    expect(mocks.toastSuccess).not.toHaveBeenCalled();
    expect(storedJourney("project-1").flowName).toBeNull();
    expect(storedJourney("project-2").flowName).toBeNull();
  });

  it("ignores a failed save that answers after the user switched project", async () => {
    const pending = deferred<never>();
    mocks.saveFlow.mockReturnValue(pending.promise);
    const view = renderPage();

    await save();
    mocks.projectId = "project-2";
    window.localStorage.setItem(PROJECT_STORAGE_KEY, "project-2");
    view.rerender();
    await act(async () => {
      pending.reject(conflict("first_calibration"));
      await pending.promise.catch(() => undefined);
    });

    expect(screen.queryByRole("alert")).toBeNull();
  });
});

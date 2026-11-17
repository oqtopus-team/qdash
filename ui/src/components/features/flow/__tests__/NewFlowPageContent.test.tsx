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
  currentUsername: "alice",
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
  useGetCurrentUser: () => ({ data: { data: { username: mocks.currentUsername } } }),
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

/** Waits for the suggested flow name, then clicks Save Flow. */
async function save() {
  await waitFor(() => expect(nameInput().value).toBe("first_calibration"));
  await act(async () => {
    fireEvent.click(screen.getByRole("button", { name: /Save Flow/ }));
  });
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
    mocks.currentUsername = "alice";
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

describe("NewFlowPageContent metadata form", () => {
  beforeEach(() => {
    mocks.projectId = "project-1";
    mocks.query.journey = null;
    window.localStorage.setItem(PROJECT_STORAGE_KEY, "project-1");
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    window.localStorage.clear();
    mocks.query.journey = "first-calibration";
    mocks.currentUsername = "alice";
  });

  /** Waits for the default template, which fills the description and the entrypoint. */
  async function waitForTemplate() {
    await waitFor(() => expect(screen.getByTestId("editor").textContent).toBe(FAKE_TEMPLATE_CODE));
  }

  /** Clicks Save Flow and lets the form validate. */
  async function clickSave() {
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: /Save Flow/ }));
    });
  }

  it("shows a missing or malformed flow name next to the field instead of saving", async () => {
    renderPage();
    await waitForTemplate();

    await clickSave();

    expect(nameInput()).toHaveAttribute("aria-invalid", "true");
    const error = document.getElementById(nameInput().getAttribute("aria-describedby") ?? "");
    expect(error).toHaveTextContent("Please enter a flow name");

    fireEvent.change(nameInput(), { target: { value: "my-flow" } });
    await waitFor(() =>
      expect(
        document.getElementById(nameInput().getAttribute("aria-describedby") ?? ""),
      ).toHaveTextContent("Flow name must contain only alphanumeric characters and underscores"),
    );

    expect(mocks.saveFlow).not.toHaveBeenCalled();
    expect(mocks.toastError).not.toHaveBeenCalled();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("opens the hidden properties panel and focuses the invalid name on Save", async () => {
    renderPage();
    await waitForTemplate();
    const toggle = screen.getAllByRole("button", { name: "Hide properties" })[0];
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    await clickSave();

    await waitFor(() => expect(document.activeElement).toBe(nameInput()));
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    expect(nameInput()).toHaveAttribute("aria-invalid", "true");
    expect(
      document.getElementById(nameInput().getAttribute("aria-describedby") ?? ""),
    ).toHaveTextContent("Please enter a flow name");
    expect(mocks.saveFlow).not.toHaveBeenCalled();
  });

  it("shows a missing username next to the field instead of saving", async () => {
    mocks.currentUsername = "";
    renderPage();
    await waitForTemplate();
    fireEvent.change(nameInput(), { target: { value: "daily_t1" } });

    await clickSave();

    const username = screen.getByLabelText("Username *");
    expect(username).toHaveAttribute("aria-invalid", "true");
    expect(
      document.getElementById(username.getAttribute("aria-describedby") ?? ""),
    ).toHaveTextContent("Please enter a username");
    expect(nameInput()).not.toHaveAttribute("aria-invalid");
    expect(mocks.saveFlow).not.toHaveBeenCalled();
    expect(mocks.toastError).not.toHaveBeenCalled();
  });

  it("submits the trimmed metadata and the normalized tags", async () => {
    mocks.saveFlow.mockResolvedValue({ data: { name: "daily_t1" } });
    renderPage();
    await waitForTemplate();
    fireEvent.change(nameInput(), { target: { value: "  daily_t1 " } });
    fireEvent.change(screen.getByPlaceholderText("Describe your flow..."), {
      target: { value: " Daily T1 check " },
    });
    fireEvent.change(screen.getByLabelText("Username *"), { target: { value: " bob " } });
    fireEvent.change(screen.getByPlaceholderText("tag1, tag2, tag3"), {
      target: { value: " t1, ,daily ,  " },
    });
    fireEvent.change(screen.getByPlaceholderText("daily/t1"), { target: { value: " daily/t1 " } });

    await clickSave();

    await waitFor(() => expect(mocks.push).toHaveBeenCalledWith("/workflow/daily_t1"));
    expect(mocks.saveFlow).toHaveBeenCalledWith({
      create_only: true,
      name: "daily_t1",
      description: "Daily T1 check",
      code: FAKE_TEMPLATE_CODE,
      flow_function_name: "fake_calibration",
      chip_id: "chip-a",
      tags: ["t1", "daily"],
      folder: "daily/t1",
      default_parameters: { username: "bob", chip_id: "chip-a" },
    });
    expect(mocks.toastError).not.toHaveBeenCalled();
  });

  it("leaves an empty entrypoint out of the request", async () => {
    mocks.saveFlow.mockResolvedValue({ data: { name: "daily_t1" } });
    renderPage();
    await waitForTemplate();
    fireEvent.change(nameInput(), { target: { value: "daily_t1" } });
    fireEvent.change(screen.getByPlaceholderText("simple_flow"), { target: { value: "  " } });

    await clickSave();

    await waitFor(() => expect(mocks.saveFlow).toHaveBeenCalledTimes(1));
    expect(mocks.saveFlow.mock.calls[0][0].flow_function_name).toBeUndefined();
    expect(mocks.saveFlow.mock.calls[0][0].tags).toEqual([]);
  });
});

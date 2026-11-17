import { useState } from "react";
import { act, cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ExecutionPageContent } from "@/components/features/execution/ExecutionPageContent";

let loadingNextPage = false;
let mockProjectId: string | null = "project-1";
const DEFAULT_DETAIL = { note: { flow_run_id: "flow-123" }, task: [] };
let executionDetail: Record<string, unknown> = DEFAULT_DETAIL;
const mockInvestigate = vi.fn();
const mockCancelMutate = vi.fn();
const mockToastSuccess = vi.fn();
const mockToastError = vi.fn();
const mockInvalidateQueries = vi.fn();

vi.mock("@tanstack/react-query", async () => {
  const actual =
    await vi.importActual<typeof import("@tanstack/react-query")>("@tanstack/react-query");
  return {
    ...actual,
    useQueryClient: () => ({ invalidateQueries: mockInvalidateQueries }),
  };
});

vi.mock("@/client/chip/chip", () => ({
  useListChips: () => ({
    data: {
      data: {
        chips: [{ chip_id: "chip-1", installed_at: "2026-06-01T00:00:00Z" }],
      },
    },
  }),
}));

vi.mock("@/client/execution/execution", () => ({
  useListExecutions: ({
    skip,
    chip_id,
    date,
  }: {
    skip: number;
    chip_id: string;
    date?: string;
  }) => ({
    data: {
      data: {
        total: date ? 0 : 40,
        executions: date
          ? [] // the API returns nothing for a day with no runs
          : skip > 0 || chip_id === "chip-2"
            ? [
                {
                  execution_id: "exec-3",
                  name: "Other Execution",
                  status: "completed",
                  start_at: "2026-06-02T00:00:00Z",
                },
              ]
            : [
                {
                  execution_id: "exec-1",
                  name: "Running Execution",
                  status: "running",
                  start_at: "2026-06-01T00:00:00Z",
                  elapsed_time: "1m",
                  username: "tester",
                },
                {
                  execution_id: "exec-2",
                  name: "Completed Execution",
                  status: "completed",
                  start_at: "2026-06-01T00:00:00Z",
                  username: "tester",
                },
              ],
      },
    },
    isError: false,
    isLoading: skip > 0 && loadingNextPage,
  }),
  useGetExecution: () => ({
    data: { data: executionDetail },
    isLoading: false,
    isError: false,
  }),
  useCancelExecution: () => ({
    mutate: mockCancelMutate,
    isPending: false,
    isError: false,
    isSuccess: false,
    error: null,
  }),
  getListExecutionsQueryKey: () => ["/executions"],
  getGetExecutionQueryKey: (executionId: string) => [`/executions/${executionId}`],
}));

vi.mock("@/contexts/ChatDockContext", () => ({
  useOptionalChatDock: () => ({ investigate: mockInvestigate }),
}));

vi.mock("@/contexts/ProjectContext", () => ({
  useProject: () => ({ projectId: mockProjectId }),
}));

vi.mock("@/hooks/useDateNavigation", () => ({
  useDateNavigation: () => undefined,
}));

vi.mock("@/hooks/useUrlState", () => ({
  useExecutionUrlState: () => {
    const [selectedChip, setSelectedChip] = useState("chip-1");
    return { selectedChip, setSelectedChip, isInitialized: true };
  },
}));

vi.mock("@/components/ui/Toast", () => ({
  useToast: () => ({
    success: mockToastSuccess,
    error: mockToastError,
    info: vi.fn(),
    warning: vi.fn(),
  }),
}));

vi.mock("next/link", () => ({
  default: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

vi.mock("@/components/features/execution/ExecutionActivityChart", () => ({
  DEFAULT_ACTIVITY_WINDOW: 30,
  ExecutionActivityChart: ({
    days,
    selectedDate,
    onDateSelect,
  }: {
    days: number;
    selectedDate: string;
    onDateSelect: (date: string) => void;
  }) => (
    <div>
      <span>ActivityChart {days}d</span>
      <span>selected:{selectedDate}</span>
      <button type="button" onClick={() => onDateSelect("20260101")}>
        pick-day
      </button>
    </div>
  ),
}));

vi.mock("@/components/charts/TaskFigure", () => ({
  TaskFigure: () => <div>TaskFigure</div>,
}));

vi.mock("@/components/selectors/ChipSelector", () => ({
  ChipSelector: ({ onChipSelect }: { onChipSelect: (chip: string) => void }) => (
    <button onClick={() => onChipSelect("chip-2")}>Change chip</button>
  ),
}));

vi.mock("@/components/selectors/DateSelector", () => ({
  DateSelector: ({ onDateSelect }: { onDateSelect: (date: string) => void }) => (
    <button onClick={() => onDateSelect("20260602")}>Change date</button>
  ),
}));

vi.mock("@/components/ui/PageContainer", () => ({
  PageContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock("@/components/ui/PageFiltersBar", () => ({
  PageFiltersBar: Object.assign(
    ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
    {
      Group: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
      Item: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
    },
  ),
}));

vi.mock("@/components/ui/PageHeader", () => ({
  PageHeader: ({ title }: { title: string }) => <h1>{title}</h1>,
}));

vi.mock("@/components/ui/Skeleton/PageSkeletons", () => ({
  ExecutionPageSkeleton: () => <div>Skeleton</div>,
}));

function openSidebarAndClickCancel() {
  // Open the sidebar for the running execution.
  fireEvent.click(screen.getByText("Running Execution"));
  // Click the list-page Cancel button inside the sidebar.
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
}

describe("ExecutionPageContent cancel confirmation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    loadingNextPage = false;
    mockProjectId = "project-1";
    executionDetail = DEFAULT_DETAIL;
    // Reset the mutate implementation so callback-driven tests don't leak into others.
    mockCancelMutate.mockReset();
  });

  afterEach(() => {
    cleanup();
  });

  it("does not cancel immediately but shows a confirmation dialog when Cancel is clicked", () => {
    render(<ExecutionPageContent />);

    openSidebarAndClickCancel();

    // The project-specific confirmation dialog is shown.
    expect(
      screen.getByText(
        "Are you sure you want to cancel this execution? This action cannot be undone.",
      ),
    ).toBeTruthy();
    // The cancellation is NOT triggered until the user confirms.
    expect(mockCancelMutate).not.toHaveBeenCalled();
  });

  it("shows the activity chart and lets it pick the day filter", () => {
    render(<ExecutionPageContent />);

    expect(screen.getByText("ActivityChart 30d")).toBeTruthy();
    expect(screen.getByText("selected:latest")).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "pick-day" }));

    expect(screen.getByText("selected:20260101")).toBeTruthy();
  });

  it("opens a non-modal details panel", () => {
    render(<ExecutionPageContent />);

    fireEvent.click(screen.getByText("Running Execution"));

    const panel = screen.getByRole("complementary", { name: "Execution details" });
    expect(panel.getAttribute("aria-hidden")).toBe("false");

    fireEvent.keyDown(document, { key: "Escape" });
    expect(panel.getAttribute("aria-hidden")).toBe("true");
  });

  it("browses adjacent executions without closing the panel and resets its scroll", () => {
    render(<ExecutionPageContent />);
    fireEvent.click(screen.getByText("Running Execution"));
    const panel = screen.getByRole("complementary", { name: "Execution details" });
    const previous = within(panel).getByRole("button", {
      name: "Previous execution",
    }) as HTMLButtonElement;
    const next = within(panel).getByRole("button", { name: "Next execution" }) as HTMLButtonElement;
    expect(previous.disabled).toBe(true);
    expect(next.disabled).toBe(false);
    expect(within(panel).getByText("1 of 2 on this page")).toBeTruthy();

    const scrollBody = within(panel).getByTestId("execution-details-scroll");
    scrollBody.scrollTop = 300;
    fireEvent.click(next);
    expect(scrollBody.scrollTop).toBe(0);
    expect(within(panel).getByRole("heading", { name: "Completed Execution" })).toBeTruthy();
    expect(within(panel).getByRole("link", { name: "View Details" }).getAttribute("href")).toBe(
      "/execution/chip-1/exec-2",
    );
    expect(within(panel).getByText("2 of 2 on this page")).toBeTruthy();
    expect(next.disabled).toBe(true);
    expect(previous.disabled).toBe(false);
    expect(within(panel).queryByRole("button", { name: "Cancel" })).toBeNull();

    fireEvent.click(previous);
    expect(within(panel).getByRole("heading", { name: "Running Execution" })).toBeTruthy();
  });

  it("moves focus into the panel and returns it to the last viewed execution on close", () => {
    render(<ExecutionPageContent />);
    const firstCard = screen.getByRole("button", {
      name: "View Running Execution execution details",
    });
    firstCard.focus();
    fireEvent.keyDown(firstCard, { key: "Enter" });
    expect(document.activeElement).toBe(
      screen.getByRole("button", { name: "Close execution details" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "Next execution" }));
    fireEvent.keyDown(document, { key: "Escape" });
    const lastCard = screen.getByRole("button", {
      name: "View Completed Execution execution details",
    });
    expect(document.activeElement).toBe(lastCard);
    expect(lastCard.getAttribute("aria-expanded")).toBe("false");
    expect(document.getElementById("execution-details-panel")?.hasAttribute("inert")).toBe(true);
  });

  it.each(["Change chip", "Next"])(
    "restores focus after %s replaces the execution list",
    (name) => {
      render(<ExecutionPageContent />);
      fireEvent.click(screen.getByText("Running Execution"));
      const panel = screen.getByRole("complementary", { name: "Execution details" });
      const scrollBody = within(panel).getByTestId("execution-details-scroll");
      scrollBody.scrollTop = 300;
      fireEvent.click(screen.getByRole("button", { name }));
      expect(document.activeElement).toBe(
        screen.getByRole("button", { name: "View Other Execution execution details" }),
      );
      expect(scrollBody.scrollTop).toBe(0);
      expect(panel.getAttribute("aria-hidden")).toBe("true");
    },
  );

  it("waits for the new page to load before restoring focus", () => {
    loadingNextPage = true;
    const { rerender } = render(<ExecutionPageContent />);
    fireEvent.click(screen.getByText("Running Execution"));
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(screen.getByText("Skeleton")).toBeTruthy();
    loadingNextPage = false;
    rerender(<ExecutionPageContent />);
    expect(document.activeElement).toBe(
      screen.getByRole("button", { name: "View Other Execution execution details" }),
    );
  });

  it("focuses the list heading when changing the date leaves no results", () => {
    render(<ExecutionPageContent />);
    fireEvent.click(screen.getByText("Running Execution"));
    fireEvent.click(screen.getByRole("button", { name: "Change date" }));
    expect(screen.getByText("No executions found")).toBeTruthy();
    expect(document.activeElement).toBe(screen.getByRole("heading", { name: "Recent executions" }));
  });

  it("returns focus to the last viewed card after navigating forward then backward", () => {
    render(<ExecutionPageContent />);
    fireEvent.click(screen.getByText("Running Execution"));
    fireEvent.click(screen.getByRole("button", { name: "Next execution" }));
    fireEvent.click(screen.getByRole("button", { name: "Previous execution" }));
    fireEvent.keyDown(document, { key: "Escape" });
    expect(document.activeElement).toBe(
      screen.getByRole("button", { name: "View Running Execution execution details" }),
    );
  });

  it("does not close the panel for Escape handled by another dialog or during composition", () => {
    render(<ExecutionPageContent />);
    fireEvent.click(screen.getByText("Running Execution"));
    const panel = screen.getByRole("complementary", { name: "Execution details" });
    fireEvent.keyDown(document, { key: "Escape", isComposing: true });
    expect(panel.getAttribute("aria-hidden")).toBe("false");
    const dialog = document.createElement("div");
    dialog.setAttribute("role", "dialog");
    document.body.appendChild(dialog);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(panel.getAttribute("aria-hidden")).toBe("false");
    dialog.remove();
  });

  it("cancels the execution with its flow_run_id after confirming in the dialog", () => {
    render(<ExecutionPageContent />);

    openSidebarAndClickCancel();
    // Confirm inside the modal.
    fireEvent.click(screen.getByRole("button", { name: "Cancel Execution" }));

    expect(mockCancelMutate).toHaveBeenCalledTimes(1);
    expect(mockCancelMutate.mock.calls[0][0]).toEqual({ flowRunId: "flow-123" });
  });

  it("closes the dialog without cancelling when Close is clicked", () => {
    render(<ExecutionPageContent />);

    openSidebarAndClickCancel();
    fireEvent.click(screen.getByRole("button", { name: "Close" }));

    expect(
      screen.queryByText(
        "Are you sure you want to cancel this execution? This action cannot be undone.",
      ),
    ).toBeNull();
    expect(mockCancelMutate).not.toHaveBeenCalled();
  });

  it("shows a success toast when the cancellation request succeeds", () => {
    mockCancelMutate.mockImplementation((_vars, { onSuccess }) => onSuccess());
    render(<ExecutionPageContent />);

    openSidebarAndClickCancel();
    fireEvent.click(screen.getByRole("button", { name: "Cancel Execution" }));

    expect(mockToastSuccess).toHaveBeenCalledWith("Cancellation requested successfully");
    expect(mockToastError).not.toHaveBeenCalled();
  });

  it("invalidates the execution list and detail queries after a successful cancellation", () => {
    mockCancelMutate.mockImplementation((_vars, { onSuccess }) => onSuccess());
    render(<ExecutionPageContent />);

    openSidebarAndClickCancel();
    fireEvent.click(screen.getByRole("button", { name: "Cancel Execution" }));

    expect(mockInvalidateQueries).toHaveBeenCalledWith({ queryKey: ["/executions"] });
    expect(mockInvalidateQueries).toHaveBeenCalledWith({ queryKey: ["/executions/exec-1"] });
  });

  it("does not invalidate any query when the cancellation request fails", () => {
    mockCancelMutate.mockImplementation((_vars, { onError }) => onError({}));
    render(<ExecutionPageContent />);

    openSidebarAndClickCancel();
    fireEvent.click(screen.getByRole("button", { name: "Cancel Execution" }));

    expect(mockInvalidateQueries).not.toHaveBeenCalled();
  });

  it("shows an error toast with the server detail when cancellation fails", () => {
    mockCancelMutate.mockImplementation((_vars, { onError }) =>
      onError({ response: { data: { detail: "Execution already finished" } } }),
    );
    render(<ExecutionPageContent />);

    openSidebarAndClickCancel();
    fireEvent.click(screen.getByRole("button", { name: "Cancel Execution" }));

    expect(mockToastError).toHaveBeenCalledWith("Execution already finished");
    expect(mockToastSuccess).not.toHaveBeenCalled();
  });

  it("shows a fallback error toast when the server provides no detail", () => {
    mockCancelMutate.mockImplementation((_vars, { onError }) => onError({}));
    render(<ExecutionPageContent />);

    openSidebarAndClickCancel();
    fireEvent.click(screen.getByRole("button", { name: "Cancel Execution" }));

    expect(mockToastError).toHaveBeenCalledWith("Failed to cancel execution");
  });
});

describe("ExecutionPageContent failure investigation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    loadingNextPage = false;
  });

  afterEach(() => {
    cleanup();
    executionDetail = DEFAULT_DETAIL;
  });

  it("opens the investigation in the floating chat, not a second sidebar", () => {
    const log = `Traceback (most recent call last):\n${"/app/qdash/workflow/calibtasks/qubex/".repeat(20)}base.py`;
    executionDetail = { status: "failed", chip_id: "chip-1", message: log, task: [] };
    render(<ExecutionPageContent />);

    fireEvent.click(screen.getByText("Running Execution"));
    const panel = screen.getByRole("complementary", { name: "Execution details" });
    // The log sits in a scrolling block beside the action, not in a squeezed alert.
    const body = within(panel).getByText((_, element) => element?.textContent === log);
    expect(body.tagName).toBe("PRE");
    expect(body.className).toContain("overflow-auto");
    expect(within(panel).getByText("Error Log").parentElement).toContainElement(
      within(panel).getByRole("button", { name: "Investigate with AI" }),
    );

    fireEvent.click(within(panel).getByRole("button", { name: "Investigate with AI" }));

    expect(mockInvestigate).toHaveBeenCalledWith(
      { executionId: "exec-1", chipId: "chip-1" },
      "mini",
    );
    // The details panel stays open underneath the floating window.
    expect(panel.getAttribute("aria-hidden")).toBe("false");
  });

  it("still offers an investigation when the failure recorded no message", () => {
    executionDetail = { status: "failed", chip_id: "chip-1", message: "", task: [] };
    render(<ExecutionPageContent />);

    fireEvent.click(screen.getByText("Running Execution"));
    const panel = screen.getByRole("complementary", { name: "Execution details" });
    expect(within(panel).getByText("No error message recorded.")).toBeTruthy();
    fireEvent.click(within(panel).getByRole("button", { name: "Investigate with AI" }));

    expect(mockInvestigate).toHaveBeenCalledWith(
      { executionId: "exec-1", chipId: "chip-1" },
      "mini",
    );
  });
});

describe("ExecutionPageContent status presentation", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    loadingNextPage = false;
  });

  afterEach(() => {
    cleanup();
    executionDetail = DEFAULT_DETAIL;
  });

  it("labels list statuses with text and a static icon instead of a pulse", () => {
    render(<ExecutionPageContent />);

    const runningCard = screen.getByRole("button", {
      name: "View Running Execution execution details",
    });
    const badge = within(runningCard).getByText("Running");
    expect(badge.className).toContain("badge-info");
    expect(badge.className).not.toContain("status-pulse");
    expect(badge.querySelector('svg[aria-hidden="true"]')).not.toBeNull();
    expect(document.querySelector(".status-pulse")).toBeNull();
  });

  it("renders task rows flat with text status cues and toggles their figures", () => {
    executionDetail = {
      ...DEFAULT_DETAIL,
      status: "running",
      task: [
        { name: "CheckRabi", qid: "0", status: "running", figure_path: ["a.png"] },
        { name: "CheckT1", qid: "1", status: "unexpected" },
      ],
    };
    render(<ExecutionPageContent />);
    fireEvent.click(screen.getByText("Running Execution"));
    const panel = screen.getByRole("complementary", { name: "Execution details" });

    const row = within(panel).getByText("0-CheckRabi").closest("h4")?.parentElement
      ?.parentElement as HTMLElement;
    const runningLabel = within(row).getByText("Running");
    expect(runningLabel.className).toContain("text-info");
    expect(runningLabel.className).not.toContain("status-pulse");
    expect(runningLabel.querySelector('svg[aria-hidden="true"]')).not.toBeNull();
    // Unknown task statuses keep reading as failed.
    const unknownRow = within(panel).getByText("1-CheckT1").closest("h4")?.parentElement
      ?.parentElement as HTMLElement;
    expect(within(unknownRow).getByText("Failed").className).toContain("text-error");
    expect(panel.querySelector(".status-pulse")).toBeNull();

    expect(row.className).not.toMatch(/shadow-(md|lg)/);
    expect(row.className).toContain("border-l-info");
    expect(within(panel).queryByText("TaskFigure")).toBeNull();

    fireEvent.click(row);
    expect(row.className).toContain("border-l-info");
    expect(within(panel).getByText("TaskFigure")).toBeTruthy();

    fireEvent.click(row);
    expect(within(panel).queryByText("TaskFigure")).toBeNull();
  });
});

describe("ExecutionPageContent floating details window", () => {
  const originalMatchMedia = window.matchMedia;
  const originalAnimate = Element.prototype.animate;
  const originalWidth = window.innerWidth;
  const originalHeight = window.innerHeight;
  let isDesktop = true;
  let reducedMotion = false;
  let mediaListeners: Array<() => void> = [];
  const animate = vi.fn();
  const pointerCaptureMethods = ["setPointerCapture", "hasPointerCapture", "releasePointerCapture"];
  const originalPointerCapture = pointerCaptureMethods.map(
    (name) => (HTMLElement.prototype as unknown as Record<string, unknown>)[name],
  );
  let captured: Set<number>;
  const releasePointerCapture = vi.fn((pointerId: number) => {
    if (!captured.delete(pointerId)) throw new DOMException("No capture", "NotFoundError");
  });

  function setViewport(width: number, height: number) {
    Object.defineProperty(window, "innerWidth", { configurable: true, value: width });
    Object.defineProperty(window, "innerHeight", { configurable: true, value: height });
  }

  function setDesktop(value: boolean) {
    isDesktop = value;
    act(() => mediaListeners.forEach((listener) => listener()));
  }

  function getPanel() {
    return document.getElementById("execution-details-panel") as HTMLElement;
  }

  function openFloatingWindow() {
    render(<ExecutionPageContent />);
    fireEvent.click(screen.getByText("Running Execution"));
    fireEvent.click(screen.getByRole("button", { name: "Float execution details" }));
    return getPanel();
  }

  beforeEach(() => {
    vi.clearAllMocks();
    loadingNextPage = false;
    mockProjectId = "project-1";
    executionDetail = DEFAULT_DETAIL;
    isDesktop = true;
    reducedMotion = false;
    mediaListeners = [];
    setViewport(1440, 900);
    window.matchMedia = ((query: string) => ({
      matches: query.includes("reduced-motion") ? reducedMotion : isDesktop,
      media: query,
      onchange: null,
      addListener: () => undefined,
      removeListener: () => undefined,
      addEventListener: (_type: string, listener: () => void) => {
        mediaListeners.push(listener);
      },
      removeEventListener: (_type: string, listener: () => void) => {
        mediaListeners = mediaListeners.filter((item) => item !== listener);
      },
      dispatchEvent: () => false,
    })) as unknown as typeof window.matchMedia;
    Element.prototype.animate = animate as unknown as typeof Element.prototype.animate;
    captured = new Set();
    Object.assign(HTMLElement.prototype, {
      setPointerCapture: (pointerId: number) => captured.add(pointerId),
      hasPointerCapture: (pointerId: number) => captured.has(pointerId),
      releasePointerCapture,
    });
  });

  afterEach(() => {
    cleanup();
    window.matchMedia = originalMatchMedia;
    Element.prototype.animate = originalAnimate;
    setViewport(originalWidth, originalHeight);
    pointerCaptureMethods.forEach((name, index) => {
      (HTMLElement.prototype as unknown as Record<string, unknown>)[name] =
        originalPointerCapture[index];
    });
  });

  function startHeaderDrag(panel: HTMLElement) {
    const move = within(panel).getByRole("button", { name: "Move execution details window" });
    const header = move.parentElement as HTMLElement;
    fireEvent.pointerDown(header, { button: 0, pointerId: 1, clientX: 500, clientY: 100 });
    fireEvent.pointerMove(header, { pointerId: 1, clientX: 400, clientY: 150 });
    return header;
  }

  it("floats the open details without losing the selection and keeps the list usable", () => {
    render(<ExecutionPageContent />);
    fireEvent.click(screen.getByText("Running Execution"));
    const panel = getPanel();
    expect(panel.dataset.mode).toBe("docked");

    fireEvent.click(within(panel).getByRole("button", { name: "Float execution details" }));

    expect(panel.dataset.mode).toBe("floating");
    expect(panel.getAttribute("aria-hidden")).toBe("false");
    expect(panel.style.width).toBe("520px");
    expect(panel.style.left).toBe(`${1440 - 520 - 32}px`);
    expect(within(panel).getByRole("heading", { name: "Running Execution" })).toBeTruthy();
    expect(document.activeElement).toBe(
      within(panel).getByRole("button", { name: "Dock execution details" }),
    );

    // The window is non-modal: picking another run swaps its content in place.
    fireEvent.click(screen.getByText("Completed Execution"));
    expect(panel.dataset.mode).toBe("floating");
    expect(within(panel).getByRole("heading", { name: "Completed Execution" })).toBeTruthy();
    expect(
      screen
        .getByRole("button", { name: "View Completed Execution execution details" })
        .getAttribute("aria-expanded"),
    ).toBe("true");
  });

  it("minimizes to a restore control and restores the same execution", () => {
    const panel = openFloatingWindow();

    fireEvent.click(within(panel).getByRole("button", { name: "Minimize execution details" }));

    expect(panel.getAttribute("aria-hidden")).toBe("true");
    expect(panel.hasAttribute("inert")).toBe(true);
    const restore = screen.getByRole("button", {
      name: "Restore execution details for Running Execution",
    });
    expect(document.activeElement).toBe(restore);
    expect(
      screen
        .getByRole("button", { name: "View Running Execution execution details" })
        .getAttribute("aria-expanded"),
    ).toBe("false");

    fireEvent.click(restore);

    expect(panel.dataset.mode).toBe("floating");
    expect(panel.getAttribute("aria-hidden")).toBe("false");
    expect(within(panel).getByRole("heading", { name: "Running Execution" })).toBeTruthy();
    expect(document.activeElement).toBe(
      within(panel).getByRole("button", { name: "Minimize execution details" }),
    );
    expect(screen.queryByRole("region", { name: "Minimized execution details" })).toBeNull();
  });

  it("restores a minimized window when another execution is picked", () => {
    const panel = openFloatingWindow();
    fireEvent.click(within(panel).getByRole("button", { name: "Minimize execution details" }));

    fireEvent.click(screen.getByText("Completed Execution"));

    expect(panel.getAttribute("aria-hidden")).toBe("false");
    expect(within(panel).getByRole("heading", { name: "Completed Execution" })).toBeTruthy();
  });

  it("closes from the minimized control, returns focus, and reopens floating", () => {
    const panel = openFloatingWindow();
    fireEvent.click(within(panel).getByRole("button", { name: "Minimize execution details" }));
    const control = screen.getByRole("region", { name: "Minimized execution details" });

    fireEvent.click(within(control).getByRole("button", { name: "Close execution details" }));

    expect(screen.queryByRole("region", { name: "Minimized execution details" })).toBeNull();
    const card = screen.getByRole("button", { name: "View Running Execution execution details" });
    expect(document.activeElement).toBe(card);
    expect(panel.getAttribute("aria-hidden")).toBe("true");

    fireEvent.click(card);
    expect(panel.dataset.mode).toBe("floating");
    expect(panel.getAttribute("aria-hidden")).toBe("false");
  });

  it("docks the window back to the right edge and moves focus to Float", () => {
    const panel = openFloatingWindow();

    fireEvent.click(within(panel).getByRole("button", { name: "Dock execution details" }));

    expect(panel.dataset.mode).toBe("docked");
    expect(panel.style.left).toBe("");
    expect(panel.className).toContain("right-0");
    expect(within(panel).getByRole("heading", { name: "Running Execution" })).toBeTruthy();
    expect(document.activeElement).toBe(
      within(panel).getByRole("button", { name: "Float execution details" }),
    );
  });

  it("takes Escape only from inside the floating window", () => {
    const panel = openFloatingWindow();

    fireEvent.keyDown(document, { key: "Escape" });
    expect(panel.getAttribute("aria-hidden")).toBe("false");

    fireEvent.keyDown(within(panel).getByRole("button", { name: "Next execution" }), {
      key: "Escape",
    });
    expect(panel.getAttribute("aria-hidden")).toBe("true");
    expect(document.activeElement).toBe(
      screen.getByRole("button", { name: "View Running Execution execution details" }),
    );
  });

  it("leaves Escape to the cancellation dialog over a floating window", () => {
    const panel = openFloatingWindow();
    fireEvent.click(within(panel).getByRole("button", { name: "Cancel" }));
    const dialog = screen.getByRole("dialog");

    fireEvent.keyDown(dialog, { key: "Escape" });

    expect(panel.getAttribute("aria-hidden")).toBe("false");
    expect(mockCancelMutate).not.toHaveBeenCalled();
  });

  it("moves and resizes with the keyboard inside the viewport", () => {
    const panel = openFloatingWindow();
    const move = within(panel).getByRole("button", { name: "Move execution details window" });
    const resize = within(panel).getByRole("button", { name: "Resize execution details window" });
    const left = parseFloat(panel.style.left);
    const top = parseFloat(panel.style.top);

    fireEvent.keyDown(move, { key: "ArrowLeft" });
    expect(panel.style.left).toBe(`${left - 16}px`);
    fireEvent.keyDown(move, { key: "ArrowDown", shiftKey: true });
    expect(panel.style.top).toBe(`${top + 64}px`);
    for (let i = 0; i < 40; i++) fireEvent.keyDown(move, { key: "ArrowRight", shiftKey: true });
    expect(panel.style.left).toBe(`${1440 - 520 - 16}px`);

    for (let i = 0; i < 20; i++) fireEvent.keyDown(resize, { key: "ArrowLeft", shiftKey: true });
    expect(panel.style.width).toBe("360px");
    for (let i = 0; i < 40; i++) fireEvent.keyDown(resize, { key: "ArrowUp", shiftKey: true });
    expect(panel.style.height).toBe("280px");

    fireEvent.keyDown(move, { key: "Home" });
    expect(panel.style.left).toBe(`${1440 - 520 - 32}px`);
    expect(panel.style.width).toBe("520px");
  });

  it("drags by the header and keeps the window on screen", () => {
    const panel = openFloatingWindow();
    const move = within(panel).getByRole("button", { name: "Move execution details window" });
    const header = move.parentElement as HTMLElement;
    const left = parseFloat(panel.style.left);
    const top = parseFloat(panel.style.top);

    fireEvent.pointerDown(header, { button: 0, pointerId: 1, clientX: 500, clientY: 100 });
    fireEvent.pointerMove(header, { pointerId: 1, clientX: 400, clientY: 150 });
    expect(panel.style.left).toBe(`${left - 100}px`);
    expect(panel.style.top).toBe(`${top + 50}px`);
    fireEvent.pointerMove(header, { pointerId: 1, clientX: -5000, clientY: -5000 });
    fireEvent.pointerUp(header, { pointerId: 1, clientX: -5000, clientY: -5000 });
    expect(panel.style.left).toBe("16px");
    expect(panel.style.top).toBe("16px");

    // Pressing the header's own buttons never starts a drag.
    fireEvent.pointerDown(within(panel).getByRole("button", { name: "Dock execution details" }), {
      button: 0,
      pointerId: 2,
      clientX: 0,
      clientY: 0,
    });
    fireEvent.pointerMove(header, { pointerId: 2, clientX: 300, clientY: 300 });
    expect(panel.style.left).toBe("16px");
  });

  it("falls back to the full-width drawer on narrow screens", () => {
    const panel = openFloatingWindow();
    fireEvent.click(within(panel).getByRole("button", { name: "Minimize execution details" }));

    setDesktop(false);

    expect(panel.dataset.mode).toBe("docked");
    expect(panel.getAttribute("aria-hidden")).toBe("false");
    expect(panel.style.left).toBe("");
    expect(within(panel).queryByRole("button", { name: "Float execution details" })).toBeNull();
    expect(screen.queryByRole("region", { name: "Minimized execution details" })).toBeNull();
    expect(within(panel).getByRole("heading", { name: "Running Execution" })).toBeTruthy();
  });

  it("ends a drag when the breakpoint docks the window, so it cannot jump when floating again", () => {
    const panel = openFloatingWindow();
    const left = parseFloat(panel.style.left);
    startHeaderDrag(panel);
    expect(captured.has(1)).toBe(true);

    setDesktop(false);

    expect(releasePointerCapture).toHaveBeenCalledWith(1);
    expect(panel.dataset.mode).toBe("docked");
    expect(panel.style.left).toBe("");

    setDesktop(true);
    const header = within(panel).getByRole("button", {
      name: "Move execution details window",
    }).parentElement as HTMLElement;
    expect(panel.dataset.mode).toBe("floating");
    expect(header.className).not.toContain("cursor-grabbing");
    // The drag ended where it got to; a stray move for the old pointer changes nothing.
    expect(panel.style.left).toBe(`${left - 100}px`);
    fireEvent.pointerMove(header, { pointerId: 1, clientX: 0, clientY: 0 });
    expect(panel.style.left).toBe(`${left - 100}px`);
  });

  it("ends a drag when pointer capture is lost or the viewport resizes", () => {
    const panel = openFloatingWindow();
    const header = startHeaderDrag(panel);
    expect(header.className).toContain("cursor-grabbing");

    fireEvent.lostPointerCapture(header, { pointerId: 1 });
    const left = panel.style.left;
    fireEvent.pointerMove(header, { pointerId: 1, clientX: 0, clientY: 0 });
    expect(panel.style.left).toBe(left);
    expect(header.className).not.toContain("cursor-grabbing");

    startHeaderDrag(panel);
    setViewport(1100, 700);
    act(() => {
      window.dispatchEvent(new Event("resize"));
    });
    expect(releasePointerCapture).toHaveBeenLastCalledWith(1);
    const fitted = panel.style.left;
    expect(parseFloat(fitted) + parseFloat(panel.style.width)).toBeLessThanOrEqual(1100 - 16);
    fireEvent.pointerMove(header, { pointerId: 1, clientX: 0, clientY: 0 });
    expect(panel.style.left).toBe(fitted);
  });

  it("releases pointer capture when unmounted mid-drag", () => {
    const panel = openFloatingWindow();
    startHeaderDrag(panel);

    cleanup();

    expect(releasePointerCapture).toHaveBeenCalledWith(1);
    expect(captured.size).toBe(0);
  });

  it("moves focus from a window control the breakpoint removes to the visible panel", () => {
    const panel = openFloatingWindow();
    within(panel).getByRole("button", { name: "Move execution details window" }).focus();

    setDesktop(false);

    expect(document.activeElement).toBe(
      within(panel).getByRole("button", { name: "Close execution details" }),
    );
  });

  it("moves focus between the panel and Restore when the breakpoint hides either", () => {
    const panel = openFloatingWindow();
    fireEvent.click(within(panel).getByRole("button", { name: "Minimize execution details" }));

    setDesktop(false);
    const close = within(panel).getByRole("button", { name: "Close execution details" });
    expect(document.activeElement).toBe(close);

    setDesktop(true);
    expect(document.activeElement).toBe(
      screen.getByRole("button", { name: "Restore execution details for Running Execution" }),
    );
  });

  it("leaves unrelated focus alone when the breakpoint changes", () => {
    const panel = openFloatingWindow();
    const card = screen.getByRole("button", { name: "View Running Execution execution details" });
    card.focus();

    setDesktop(false);

    expect(document.activeElement).toBe(card);
    expect(panel.dataset.mode).toBe("docked");
  });

  it("closes the panel and pending cancellation when the project switches to the same chip ID", () => {
    const { rerender } = render(<ExecutionPageContent />);
    fireEvent.click(screen.getByText("Running Execution"));
    const panel = getPanel();
    fireEvent.click(within(panel).getByRole("button", { name: "Cancel" }));
    expect(screen.getByRole("dialog")).toBeTruthy();

    mockProjectId = "project-2";
    rerender(<ExecutionPageContent />);

    expect(panel.getAttribute("aria-hidden")).toBe("true");
    expect(within(panel).queryByRole("heading", { name: "Running Execution" })).toBeNull();
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(mockCancelMutate).not.toHaveBeenCalled();
  });

  it("returns focus to the list only when the switched-away panel had it", () => {
    const { rerender } = render(<ExecutionPageContent />);
    fireEvent.click(screen.getByText("Running Execution"));
    const card = screen.getByRole("button", { name: "View Running Execution execution details" });

    mockProjectId = "project-2";
    rerender(<ExecutionPageContent />);
    expect(document.activeElement).toBe(card);

    fireEvent.click(card);
    const heading = screen.getByRole("heading", { name: "Recent executions" });
    heading.focus();
    mockProjectId = "project-3";
    rerender(<ExecutionPageContent />);
    expect(getPanel().getAttribute("aria-hidden")).toBe("true");
    expect(document.activeElement).toBe(heading);
  });

  it("resets the picked day on a project switch but not when the project first resolves", () => {
    mockProjectId = null;
    const { rerender } = render(<ExecutionPageContent />);
    fireEvent.click(screen.getByText("Running Execution"));

    mockProjectId = "project-1";
    rerender(<ExecutionPageContent />);
    expect(getPanel().getAttribute("aria-hidden")).toBe("false");

    fireEvent.click(screen.getByRole("button", { name: "pick-day" }));
    expect(screen.getByText("selected:20260101")).toBeTruthy();
    mockProjectId = "project-2";
    rerender(<ExecutionPageContent />);
    expect(screen.getByText("selected:latest")).toBeTruthy();
  });

  it("closes the window when the chip changes", () => {
    const panel = openFloatingWindow();

    fireEvent.click(screen.getByRole("button", { name: "Change chip" }));

    expect(panel.getAttribute("aria-hidden")).toBe("true");
    expect(within(panel).queryByRole("heading", { name: "Running Execution" })).toBeNull();
  });

  it("animates mode changes and skips motion when reduced motion is preferred", () => {
    const panel = openFloatingWindow();
    expect(animate).toHaveBeenCalledTimes(1);
    fireEvent.click(within(panel).getByRole("button", { name: "Minimize execution details" }));
    expect(animate).toHaveBeenCalledTimes(2);
    cleanup();

    animate.mockClear();
    reducedMotion = true;
    const reducedPanel = openFloatingWindow();
    fireEvent.click(
      within(reducedPanel).getByRole("button", { name: "Minimize execution details" }),
    );
    fireEvent.click(
      screen.getByRole("button", { name: "Restore execution details for Running Execution" }),
    );
    expect(reducedPanel.dataset.mode).toBe("floating");
    expect(animate).not.toHaveBeenCalled();
  });
});

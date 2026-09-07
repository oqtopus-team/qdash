import { useState } from "react";
import { cleanup, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ExecutionPageContent } from "@/components/features/execution/ExecutionPageContent";

let loadingNextPage = false;
const mockCancelMutate = vi.fn();
const mockToastSuccess = vi.fn();
const mockToastError = vi.fn();

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
  useListExecutions: ({ skip, chip_id }: { skip: number; chip_id: string }) => ({
    data: {
      data: {
        total: 40,
        executions:
          skip > 0 || chip_id === "chip-2"
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
    data: {
      data: {
        note: { flow_run_id: "flow-123" },
        task: [],
      },
    },
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

vi.mock("@/components/features/execution/ExecutionDurationBreakdown", () => ({
  ExecutionDurationBreakdown: () => <div>DurationBreakdown</div>,
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

  it("loads the duration breakdown only after it is expanded", () => {
    render(<ExecutionPageContent />);

    expect(screen.queryByText("DurationBreakdown")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /Task duration breakdown/i }));

    expect(screen.getByText("DurationBreakdown")).toBeTruthy();
  });

  it("summarizes the current executions and opens a non-modal details panel", () => {
    render(<ExecutionPageContent />);

    const summary = screen.getByRole("region", { name: "Execution status summary" });
    expect(within(summary).getByText("Total")).toBeTruthy();
    expect(within(summary).getByText("Running")).toBeTruthy();

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

    panel.scrollTop = 300;
    fireEvent.click(next);
    expect(panel.scrollTop).toBe(0);
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
      panel.scrollTop = 300;
      fireEvent.click(screen.getByRole("button", { name }));
      expect(document.activeElement).toBe(
        screen.getByRole("button", { name: "View Other Execution execution details" }),
      );
      expect(panel.scrollTop).toBe(0);
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

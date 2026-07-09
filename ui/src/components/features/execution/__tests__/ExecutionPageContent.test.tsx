import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ExecutionPageContent } from "@/components/features/execution/ExecutionPageContent";

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
  useListExecutions: () => ({
    data: {
      data: {
        executions: [
          {
            execution_id: "exec-1",
            name: "Running Execution",
            status: "running",
            start_at: "2026-06-01T00:00:00Z",
            elapsed_time: "1m",
            username: "tester",
          },
        ],
      },
    },
    isError: false,
    isLoading: false,
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
  useExecutionUrlState: () => ({
    selectedChip: "chip-1",
    setSelectedChip: vi.fn(),
    isInitialized: true,
  }),
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
  ChipSelector: () => <div>ChipSelector</div>,
}));

vi.mock("@/components/selectors/DateSelector", () => ({
  DateSelector: () => <div>DateSelector</div>,
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

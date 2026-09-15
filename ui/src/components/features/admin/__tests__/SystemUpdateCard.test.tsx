import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SystemUpdateCard } from "@/components/features/admin/SystemUpdateCard";

const mocks = vi.hoisted(() => ({
  enabled: true,
  mutate: vi.fn(),
  refetch: vi.fn(),
  refetchOperation: vi.fn(),
  operationError: false,
  invalidateQueries: vi.fn(),
  status: {
    enabled: true,
    current_version: "v1.9.12",
    current_commit: "abc1234567890123",
    latest_version: "v1.9.13",
    update_available: true,
    can_update: true,
    dirty: false,
    blocked_reason: null,
    operation_id: null,
    operation_state: "idle",
    checked_at: "2026-09-13T00:00:00Z",
  },
}));

vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries: mocks.invalidateQueries }),
}));

vi.mock("@/client/admin/admin", () => ({
  getGetSystemUpdateStatusQueryKey: () => ["system-update-status"],
  useGetSystemUpdateStatus: () => ({
    data: { data: { ...mocks.status, enabled: mocks.enabled } },
    isLoading: false,
    isFetching: false,
    isError: false,
    refetch: mocks.refetch,
  }),
  useGetSystemUpdateOperation: () => ({
    data: undefined,
    isError: mocks.operationError,
    refetch: mocks.refetchOperation,
  }),
  useStartSystemUpdate: () => ({
    mutate: mocks.mutate,
    isPending: false,
    isError: false,
  }),
}));

vi.mock("@/components/ui/ConfirmDialog", () => ({
  ConfirmDialog: ({ open, onConfirm }: { open: boolean; onConfirm: () => void }) =>
    open ? <button onClick={onConfirm}>Confirm update</button> : null,
}));

describe("SystemUpdateCard", () => {
  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    window.localStorage.clear();
    mocks.enabled = true;
    mocks.operationError = false;
  });

  it("shows current and latest stable releases", () => {
    render(<SystemUpdateCard />);

    expect(screen.getByText("v1.9.12")).toBeTruthy();
    expect(screen.getByText("v1.9.13")).toBeTruthy();
    expect(screen.getByRole("button", { name: "Update to v1.9.13" })).toBeEnabled();
  });

  it("confirms the expected current release before starting", () => {
    render(<SystemUpdateCard />);

    fireEvent.click(screen.getByRole("button", { name: "Update to v1.9.13" }));
    fireEvent.click(screen.getByRole("button", { name: "Confirm update" }));

    expect(mocks.mutate).toHaveBeenCalledWith({
      data: { expected_current_version: "v1.9.12" },
    });
  });

  it("shows a task-independent startup command when the updater is unavailable", () => {
    mocks.enabled = false;

    render(<SystemUpdateCard />);

    expect(
      screen.getByText("uv run --env-file .env --isolated --locked --no-dev qdash-updater start"),
    ).toBeTruthy();
  });

  it("lets an admin dismiss an unavailable saved operation", () => {
    window.localStorage.setItem("qdash-system-update-operation", "missing-operation");
    mocks.operationError = true;

    render(<SystemUpdateCard />);
    fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));

    expect(window.localStorage.getItem("qdash-system-update-operation")).toBeNull();
    expect(screen.getByRole("button", { name: "Update to v1.9.13" })).toBeEnabled();
  });
});

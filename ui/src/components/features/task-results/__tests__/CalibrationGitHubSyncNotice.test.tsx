import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { CalibrationGitHubSyncNotice } from "@/components/features/task-results/CalibrationGitHubSyncNotice";

const mocks = vi.hoisted(() => ({ mutate: vi.fn() }));
vi.mock("@/client/calibration/calibration", () => ({
  useRetryCalibrationGitHubSync: () => ({ mutate: mocks.mutate, isPending: false, isError: false }),
}));
afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

describe("CalibrationGitHubSyncNotice", () => {
  it("keeps applied status visible and retries synchronization only", () => {
    mocks.mutate.mockImplementation((_input, options) =>
      options.onSuccess({ data: { status: "synced", commit: "abc123" } }),
    );
    render(
      <CalibrationGitHubSyncNotice
        result={{ task_id: "manual-edit-1", github_sync: { status: "failed" } }}
      />,
    );
    expect(screen.getByRole("status").textContent).toContain("Values are applied");
    fireEvent.click(screen.getByRole("button", { name: "Retry GitHub sync" }));
    expect(mocks.mutate.mock.calls[0][0]).toEqual({ taskId: "manual-edit-1" });
    expect(screen.getByText("GitHub synchronized.")).not.toBeNull();
    expect(screen.queryByRole("button")).toBeNull();
  });

  it("does not offer synchronization when disabled", () => {
    const { container } = render(
      <CalibrationGitHubSyncNotice
        result={{ task_id: "manual-edit-1", github_sync: { status: "disabled" } }}
      />,
    );
    expect(container.innerHTML).toBe("");
  });
});

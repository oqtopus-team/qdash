import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { HomePageContent } from "@/components/features/home/HomePageContent";

const mockExecutionLock = vi.hoisted(() => vi.fn());
const mockChips = vi.hoisted(() => vi.fn());
const mockTaskResults = vi.hoisted(() => vi.fn());
const mockNotifications = vi.hoisted(() => vi.fn());

vi.mock("@/client/execution/execution", () => ({
  useGetExecutionLockStatus: mockExecutionLock,
}));

vi.mock("@/client/chip/chip", () => ({
  useListChips: mockChips,
}));

vi.mock("@/client/task-result/task-result", () => ({
  useListTaskResults: mockTaskResults,
}));

vi.mock("@/contexts/ProjectContext", () => ({
  useProject: () => ({ canEdit: true }),
}));

vi.mock("@/hooks/useNotifications", () => ({
  useNotifications: mockNotifications,
  useNotificationActions: () => ({ markRead: { mutate: vi.fn() } }),
}));

describe("HomePageContent", () => {
  beforeEach(() => {
    mockChips.mockReturnValue({
      data: { data: { chips: [{ chip_id: "chip-1" }] } },
      isLoading: false,
      error: null,
    });
    mockExecutionLock.mockReturnValue({
      data: {
        data: {
          lock: true,
          execution_id: "execution-1",
          chip_id: "chip-1",
          name: "Daily calibration",
          status: "running",
        },
      },
      isLoading: false,
    });
    mockTaskResults.mockReturnValue({
      data: {
        data: {
          items: [
            {
              task_id: "task-1",
              task_name: "CheckRabi",
              qid: "Q0",
              chip_id: "chip-1",
              status: "failed",
              execution_id: "execution-1",
              message: "Fit failed",
            },
          ],
        },
      },
      isLoading: false,
      error: null,
    });
    mockNotifications.mockReturnValue({
      data: {
        data: {
          notifications: [
            {
              id: "notification-1",
              kind: "forum_reply",
              title: "A new reply",
              excerpt: "Please review this result",
              actor_username: "alice",
              created_at: new Date().toISOString(),
              target_url: "/forum/post-1",
              read_at: null,
            },
          ],
        },
      },
      isLoading: false,
      error: null,
    });
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
  });

  it("summarizes active work and items that need attention", () => {
    render(<HomePageContent />);

    expect(screen.getByRole("heading", { name: "Home" })).toBeTruthy();
    expect(screen.getByText("Daily calibration")).toBeTruthy();
    expect(screen.getByText("CheckRabi")).toBeTruthy();
    expect(screen.getByText("A new reply")).toBeTruthy();
    expect(screen.getByRole("link", { name: /Run a task/ }).getAttribute("href")).toBe("/tasks");
    expect(screen.getByRole("link", { name: /View inbox/ }).getAttribute("href")).toBe("/inbox");
    expect(screen.getByRole("link", { name: "Setup tour" }).getAttribute("href")).toBe(
      "/chip?tutorial=create-chip",
    );
  });

  it("keeps the home grids single column until the layout breakpoints", () => {
    const { container } = render(<HomePageContent />);

    const quickActions = container.querySelector("[aria-labelledby='quick-actions-heading'] > div");
    expect(quickActions?.className).toContain("grid-cols-1");

    const overview = container.querySelector('[class*="xl:grid-cols-[minmax(0,1.15fr)"]');
    expect(overview?.className).toContain("grid-cols-1");
  });

  it("shows calm empty states when no work is waiting", () => {
    mockExecutionLock.mockReturnValue({
      data: { data: { lock: false } },
      isLoading: false,
    });
    mockTaskResults.mockReturnValue({
      data: { data: { items: [] } },
      isLoading: false,
      error: null,
    });
    mockNotifications.mockReturnValue({
      data: { data: { notifications: [] } },
      isLoading: false,
      error: null,
    });

    render(<HomePageContent />);

    expect(screen.getByText("No calibration is running")).toBeTruthy();
    expect(screen.getByText("No failed task results")).toBeTruthy();
    expect(screen.getByText("You are all caught up")).toBeTruthy();
  });

  it("prominently offers setup when the project has no chips", () => {
    mockChips.mockReturnValue({
      data: { data: { chips: [] } },
      isLoading: false,
      error: null,
    });

    render(<HomePageContent />);

    expect(screen.getByRole("heading", { name: "Create your first chip" })).toBeTruthy();
    expect(screen.getByRole("link", { name: "Start setup tour" }).getAttribute("href")).toBe(
      "/chip?tutorial=create-chip",
    );
    expect(screen.queryByRole("link", { name: "Setup tour" })).toBeNull();
  });
});

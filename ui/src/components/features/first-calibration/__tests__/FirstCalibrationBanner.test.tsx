import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FirstCalibrationBanner } from "@/components/features/first-calibration/FirstCalibrationBanner";
import { journeyStorageKey } from "@/lib/firstCalibrationJourney";

const mocks = vi.hoisted(() => ({
  pathname: "/execution/chip-a/20261105-001",
  execution: undefined as Record<string, unknown> | undefined,
}));

vi.mock("next/navigation", () => ({
  usePathname: () => mocks.pathname,
}));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ username: "alice" }),
}));

vi.mock("@/contexts/ProjectContext", () => ({
  useProject: () => ({ projectId: "project-1", canEdit: true }),
}));

vi.mock("@/client/chip/chip", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  useListChips: () => ({
    data: { data: { chips: [{ chip_id: "chip-a", size: 64 }] } },
    isError: false,
  }),
  useListChipConfigSources: () => ({
    data: {
      data: {
        available: true,
        sources: [],
        deployment_backend: "fake",
        presets: [],
      },
    },
    isError: false,
  }),
}));

vi.mock("@/client/flow/flow", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  useGetFlow: () => ({
    data: { data: { name: "first_calibration", chip_id: "chip-a" } },
    isLoading: false,
    isError: false,
    error: null,
  }),
}));

vi.mock("@/client/execution/execution", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  useGetExecution: () => ({
    data: mocks.execution ? { data: mocks.execution } : undefined,
    isLoading: !mocks.execution,
    isError: false,
    error: null,
  }),
}));

const KEY = journeyStorageKey("alice", "project-1");

function storeJourney(overrides: Record<string, unknown> = {}) {
  window.localStorage.setItem(
    KEY,
    JSON.stringify({
      version: 1,
      status: "active",
      chipId: "chip-a",
      flowName: "first_calibration",
      executionId: "20261105-001",
      hardwareConfirmedChipId: null,
      inspectedTaskId: null,
      chipOverviewSeen: false,
      startedAt: "2026-11-05T00:00:00.000Z",
      updatedAt: "2026-11-05T00:00:00.000Z",
      ...overrides,
    }),
  );
}

describe("FirstCalibrationBanner", () => {
  beforeEach(() => {
    mocks.pathname = "/execution/chip-a/20261105-001";
    mocks.execution = {
      name: "run",
      status: "running",
      chip_id: "chip-a",
      task: [
        { name: "CheckT1", status: "completed", task_id: "t1" },
        { name: "CheckT2Echo", status: "running", task_id: "t2" },
      ],
      note: {},
    };
  });

  afterEach(() => {
    cleanup();
    window.localStorage.clear();
  });

  it("renders nothing without a journey", () => {
    const { container } = render(<FirstCalibrationBanner />);
    expect(container).toBeEmptyDOMElement();
  });

  it("leaves Home to the journey card", () => {
    storeJourney();
    mocks.pathname = "/home";
    const { container } = render(<FirstCalibrationBanner />);
    expect(container).toBeEmptyDOMElement();
  });

  it("follows the run without linking to the page that is already open", () => {
    storeJourney();
    render(<FirstCalibrationBanner />);

    expect(screen.getByRole("region", { name: "First calibration guide" })).toBeTruthy();
    expect(screen.getByText(/Step 3 of 5/)).toBeTruthy();
    expect(screen.getByText("Running: 1 of 2 tasks completed.")).toBeTruthy();
    expect(screen.queryByRole("link", { name: "Follow progress" })).toBeNull();
  });

  it("links to the run from other pages", () => {
    storeJourney();
    mocks.pathname = "/workflow/first_calibration";
    render(<FirstCalibrationBanner />);

    expect(screen.getByRole("link", { name: "Follow progress" })).toHaveAttribute(
      "href",
      "/execution/chip-a/20261105-001",
    );
  });

  it("offers a retry and the failed run instead of the result step", () => {
    storeJourney();
    mocks.execution = {
      ...mocks.execution,
      status: "failed",
      message: "Box unreachable",
    };
    render(<FirstCalibrationBanner />);

    expect(screen.getByText("The run failed: Box unreachable")).toBeTruthy();
    expect(screen.getByRole("link", { name: "Run again" })).toHaveAttribute(
      "href",
      "/workflow/first_calibration",
    );
    expect(screen.queryByRole("link", { name: /result/ })).toBeNull();
  });

  it("points at the CheckT1 result once the run succeeds", () => {
    storeJourney();
    mocks.execution = {
      ...mocks.execution,
      status: "completed",
      task: [
        {
          name: "CheckT1",
          status: "completed",
          task_id: "t1",
          figure_path: ["t1.png"],
        },
      ],
    };
    render(<FirstCalibrationBanner />);

    expect(screen.getByText(/Step 4 of 5/)).toBeTruthy();
    expect(screen.getByRole("link", { name: "Open CheckT1 result" })).toHaveAttribute(
      "href",
      "/task-results/t1",
    );
  });

  it("pauses the journey on exit so Home can resume it", () => {
    storeJourney();
    render(<FirstCalibrationBanner />);

    fireEvent.click(screen.getByRole("button", { name: "Exit guide" }));

    expect(JSON.parse(window.localStorage.getItem(KEY) ?? "{}").status).toBe("paused");
    expect(screen.queryByRole("region", { name: "First calibration guide" })).toBeNull();
  });
});

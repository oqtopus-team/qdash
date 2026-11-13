import { act, cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useChipPageJourney } from "@/components/features/first-calibration/useChipPageJourney";
import { journeyStorageKey } from "@/lib/firstCalibrationJourney";

const FAKE_SETUP = {
  kind: "preset",
  backend: "fake",
  configAvailable: true,
  preset: {
    preset_id: "fake",
    name: "Virtual fake device",
    description: "",
    topology_id: "square-lattice-mux-64",
    n_qubits: 64,
    mux_count: 16,
    workflow_template_id: "fake_calibration",
  },
};
const HARDWARE_SETUP = { kind: "hardware", configAvailable: true };

const mocks = vi.hoisted(() => ({
  search: "",
  replace: vi.fn(),
  push: vi.fn(),
  canEdit: true,
  projectId: "project-1",
  setup: null as unknown,
}));

vi.mock("next/navigation", () => ({
  useRouter: () => ({ replace: mocks.replace, push: mocks.push }),
  useSearchParams: () => new URLSearchParams(mocks.search),
}));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ username: "alice" }),
}));

vi.mock("@/contexts/ProjectContext", () => ({
  useProject: () => ({ projectId: mocks.projectId, canEdit: mocks.canEdit }),
}));

vi.mock("@/components/features/first-calibration/useFirstCalibrationProgress", () => ({
  useFirstCalibrationProgress: () => ({ setup: mocks.setup }),
}));

const PROJECT_STORAGE_KEY = "qdash_current_project_id";

const KEY = journeyStorageKey("alice", "project-1");

function storeJourney(overrides: Record<string, unknown> = {}) {
  window.localStorage.setItem(
    KEY,
    JSON.stringify({
      version: 1,
      status: "active",
      chipId: null,
      flowName: null,
      executionId: null,
      hardwareConfirmedChipId: null,
      inspectedTaskId: null,
      chipOverviewSeen: false,
      startedAt: "2026-11-05T00:00:00.000Z",
      updatedAt: "2026-11-05T00:00:00.000Z",
      ...overrides,
    }),
  );
}

function stored() {
  return JSON.parse(window.localStorage.getItem(KEY) ?? "null");
}

describe("useChipPageJourney", () => {
  beforeEach(() => {
    mocks.search = "";
    mocks.canEdit = true;
    mocks.projectId = "project-1";
    mocks.setup = FAKE_SETUP;
    window.localStorage.setItem(PROJECT_STORAGE_KEY, "project-1");
    window.history.replaceState(null, "", "/chip?journey=create-chip");
  });

  afterEach(() => {
    cleanup();
    vi.clearAllMocks();
    window.localStorage.clear();
  });

  it("turns the retired setup tour link into the journey's chip step", () => {
    mocks.search = "tutorial=create-chip&chip=old";
    renderHook(() => useChipPageJourney({ selectedChip: "old", openCreateChip: vi.fn() }));

    expect(stored()).toMatchObject({ status: "active", chipId: null });
    expect(mocks.replace).toHaveBeenLastCalledWith("/chip?chip=old&journey=create-chip", {
      scroll: false,
    });
  });

  it("resumes a paused journey from the old link without asking for a new chip", () => {
    storeJourney({ status: "paused", chipId: "chip-a" });
    mocks.search = "tutorial=create-chip";
    renderHook(() => useChipPageJourney({ selectedChip: null, openCreateChip: vi.fn() }));

    expect(stored()).toMatchObject({ status: "active", chipId: "chip-a" });
    expect(mocks.replace).toHaveBeenLastCalledWith("/chip", { scroll: false });
  });

  it("only strips the old link for a viewer", () => {
    mocks.canEdit = false;
    mocks.search = "tutorial=create-chip";
    renderHook(() => useChipPageJourney({ selectedChip: null, openCreateChip: vi.fn() }));

    expect(stored()).toBeNull();
    expect(mocks.replace).toHaveBeenCalledWith("/chip", { scroll: false });
  });

  it("opens the Create Chip dialog once and adopts the created chip", () => {
    storeJourney({ chipId: "deleted-chip" });
    mocks.search = "journey=create-chip";
    mocks.setup = HARDWARE_SETUP;
    const openCreateChip = vi.fn();
    const { result, rerender } = renderHook(() =>
      useChipPageJourney({ selectedChip: null, openCreateChip }),
    );
    rerender();
    expect(openCreateChip).toHaveBeenCalledTimes(1);
    expect(result.current.adoptsCreatedChip).toBe(true);

    const submission = result.current.captureCreateSubmission();
    let outcome: string | undefined;
    act(() => {
      outcome = result.current.onChipCreated("chip-new", submission);
    });
    expect(stored().chipId).toBe("chip-new");
    // Hardware: the readiness check comes before the editor, so the user stays here.
    expect(outcome).toBe("stay");
    expect(mocks.push).not.toHaveBeenCalled();

    act(() => result.current.onCreateChipClosed());
    expect(mocks.replace).toHaveBeenLastCalledWith("/chip", { scroll: false });
  });

  it("opens the fake template for the created chip once, keeping the chip page behind it", () => {
    storeJourney();
    mocks.search = "journey=create-chip";
    const { result, rerender } = renderHook(() =>
      useChipPageJourney({ selectedChip: null, openCreateChip: vi.fn() }),
    );
    rerender();
    const submission = result.current.captureCreateSubmission();

    expect(result.current.leavingForGuide).toBe(false);
    let outcome: string | undefined;
    act(() => {
      outcome = result.current.onChipCreated("fake-1", submission);
    });
    expect(outcome).toBe("navigate");
    // The page stops writing its URL state, which would cancel the push below.
    expect(result.current.leavingForGuide).toBe(true);
    expect(stored()).toMatchObject({ status: "active", chipId: "fake-1" });
    expect(mocks.push).toHaveBeenCalledTimes(1);
    expect(mocks.push).toHaveBeenCalledWith(
      "/workflow/new?backend=fake&template=fake_calibration&chip_id=fake-1&journey=first-calibration",
    );
    // Back returns to the Chip page on the new chip, not to the reopened dialog.
    expect(window.location.pathname + window.location.search).toBe("/chip?chip=fake-1");

    // The dialog closes after the answer; that close must not replace the editor route.
    act(() => result.current.onCreateChipClosed());
    expect(mocks.replace).not.toHaveBeenCalled();

    // A repeated answer for the same chip does not navigate again.
    act(() => {
      result.current.onChipCreated("fake-1", submission);
    });
    expect(mocks.push).toHaveBeenCalledTimes(1);
  });

  it("neither records nor navigates when the guide was paused while the chip was created", () => {
    storeJourney();
    mocks.search = "journey=create-chip";
    const { result } = renderHook(() =>
      useChipPageJourney({ selectedChip: null, openCreateChip: vi.fn() }),
    );
    const submission = result.current.captureCreateSubmission();
    act(() => {
      storeJourney({ status: "paused" });
      window.dispatchEvent(new Event("storage"));
    });

    let outcome: string | undefined;
    act(() => {
      outcome = result.current.onChipCreated("fake-1", submission);
    });
    expect(outcome).toBe("stay");
    expect(stored()).toMatchObject({ status: "paused", chipId: null });
    expect(mocks.push).not.toHaveBeenCalled();
  });

  it("neither records nor navigates when the user switched project while the chip was created", () => {
    storeJourney();
    mocks.search = "journey=create-chip";
    const { result, rerender } = renderHook(() =>
      useChipPageJourney({ selectedChip: null, openCreateChip: vi.fn() }),
    );
    const submission = result.current.captureCreateSubmission();
    window.localStorage.setItem(PROJECT_STORAGE_KEY, "project-2");
    mocks.projectId = "project-2";
    rerender();

    let outcome: string | undefined;
    act(() => {
      outcome = result.current.onChipCreated("fake-1", submission);
    });
    expect(outcome).toBe("stay");
    expect(stored().chipId).toBeNull();
    expect(mocks.push).not.toHaveBeenCalled();
  });

  it("leaves the journey's chip alone when a routine chip is created", () => {
    storeJourney({ chipId: "chip-a" });
    const { result } = renderHook(() =>
      useChipPageJourney({ selectedChip: "chip-a", openCreateChip: vi.fn() }),
    );

    expect(result.current.adoptsCreatedChip).toBe(false);
    const submission = result.current.captureCreateSubmission();
    let outcome: string | undefined;
    act(() => {
      outcome = result.current.onChipCreated("chip-routine", submission);
    });
    expect(outcome).toBe("stay");
    expect(stored().chipId).toBe("chip-a");
    expect(mocks.push).not.toHaveBeenCalled();
  });

  it("finishes on the overview of the journey's chip only after a result was inspected", () => {
    storeJourney({
      chipId: "chip-a",
      flowName: "first_calibration",
      executionId: "20261105-001",
    });
    const { rerender } = renderHook(
      ({ chip }) => useChipPageJourney({ selectedChip: chip, openCreateChip: vi.fn() }),
      { initialProps: { chip: "chip-a" } },
    );
    expect(stored().chipOverviewSeen).toBe(false);

    rerender({ chip: "other-chip" });
    act(() => {
      storeJourney({
        chipId: "chip-a",
        flowName: "first_calibration",
        executionId: "20261105-001",
        inspectedTaskId: "t1",
      });
      window.dispatchEvent(new Event("storage"));
    });
    expect(stored().chipOverviewSeen).toBe(false);

    rerender({ chip: "chip-a" });
    expect(stored().chipOverviewSeen).toBe(true);
  });
});

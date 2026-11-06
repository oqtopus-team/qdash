import { cleanup, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { useFirstCalibrationJourney } from "@/components/features/first-calibration/useFirstCalibrationJourney";

import { PROJECT_STORAGE_KEY, storeJourney, storedJourney } from "./journeyTestUtils";

const session = vi.hoisted(() => ({
  username: "alice",
  projectId: "project-1",
  canEdit: true,
}));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ username: session.username }),
}));

vi.mock("@/contexts/ProjectContext", () => ({
  useProject: () => ({
    projectId: session.projectId,
    canEdit: session.canEdit,
  }),
}));

function switchProject(projectId: string) {
  session.projectId = projectId;
  window.localStorage.setItem(PROJECT_STORAGE_KEY, projectId);
}

describe("useFirstCalibrationJourney capture", () => {
  beforeEach(() => {
    session.username = "alice";
    session.canEdit = true;
    switchProject("project-1");
    storeJourney("project-1", { chipId: "chip-a" });
    storeJourney("project-2", { chipId: "chip-a" });
  });

  afterEach(() => {
    cleanup();
    window.localStorage.clear();
  });

  it("records an answer in the context it was submitted in", () => {
    const { result } = renderHook(() => useFirstCalibrationJourney());
    const context = result.current.capture();

    expect(context.isCurrent()).toBe(true);
    context.record({
      type: "flowSaved",
      flowName: "first_calibration",
      chipId: "chip-a",
    });

    expect(storedJourney("project-1").flowName).toBe("first_calibration");
  });

  it("drops an answer that lands after a project switch", () => {
    const { result, rerender } = renderHook(() => useFirstCalibrationJourney());
    const context = result.current.capture();

    switchProject("project-2");
    rerender();
    context.record({
      type: "flowSaved",
      flowName: "first_calibration",
      chipId: "chip-a",
    });

    expect(context.isCurrent()).toBe(false);
    expect(storedJourney("project-1").flowName).toBeNull();
    expect(storedJourney("project-2").flowName).toBeNull();
  });

  it("treats the switch as done once the request header changes, before React renders it", () => {
    const { result } = renderHook(() => useFirstCalibrationJourney());
    const context = result.current.capture();

    // ProjectContext writes the new project to storage first; the render follows.
    window.localStorage.setItem(PROJECT_STORAGE_KEY, "project-2");

    expect(context.isCurrent()).toBe(false);
  });

  it("drops an answer for another signed-in user", () => {
    const { result, rerender } = renderHook(() => useFirstCalibrationJourney());
    const context = result.current.capture();

    session.username = "bob";
    rerender();

    expect(context.isCurrent()).toBe(false);
  });

  it("drops an answer that lands after the page unmounted", () => {
    const { result, unmount } = renderHook(() => useFirstCalibrationJourney());
    const context = result.current.capture();

    unmount();
    context.record({
      type: "flowSaved",
      flowName: "first_calibration",
      chipId: "chip-a",
    });

    expect(context.isCurrent()).toBe(false);
    expect(storedJourney("project-1").flowName).toBeNull();
  });
});

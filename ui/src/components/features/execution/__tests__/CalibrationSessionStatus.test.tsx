import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import {
  CalibrationSessionStatusBadge,
  calibrationSessionStatusStyle,
} from "@/components/features/execution/CalibrationSessionStatus";
import {
  getStatusBadgeClass,
  getStatusBorderStyle,
} from "@/components/features/execution/ExecutionListCard";

afterEach(cleanup);

describe("calibration session status", () => {
  it("reads an open session like an active execution", () => {
    const open = calibrationSessionStatusStyle("open");
    expect(open.label).toBe("Open");
    expect(open.badge).toBe(getStatusBadgeClass("running"));
    expect(open.border).toBe(getStatusBorderStyle("running"));
  });

  it("never gives a closed session the outcome colors of a completed or failed execution", () => {
    const closed = calibrationSessionStatusStyle("closed");
    expect(closed.label).toBe("Closed");
    for (const outcome of ["completed", "failed"]) {
      expect(closed.badge).not.toBe(getStatusBadgeClass(outcome));
      expect(closed.border).not.toBe(getStatusBorderStyle(outcome));
    }
    // It ends like a cancelled execution: the neutral accent of work that stopped.
    expect(closed.border).toBe(getStatusBorderStyle("cancelled"));
  });

  it("names the state in text, not by color alone", () => {
    render(<CalibrationSessionStatusBadge status="closed" />);
    expect(screen.getByText("Closed")).toBeTruthy();
  });
});

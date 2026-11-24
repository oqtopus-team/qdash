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

  it("reads a closed session like a completed execution, since all of its work ended", () => {
    const closed = calibrationSessionStatusStyle("closed");
    expect(closed.label).toBe("Closed");
    expect(closed.badge).toBe(getStatusBadgeClass("completed"));
    expect(closed.border).toBe(getStatusBorderStyle("completed"));
  });

  it("names the state in text, not by color alone", () => {
    render(<CalibrationSessionStatusBadge status="closed" />);
    expect(screen.getByText("Closed")).toBeTruthy();
  });
});

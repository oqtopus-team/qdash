import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { TimeRangeSelector } from "@/components/ui/TimeRangeSelector";

const props = {
  startDate: "2026-08-01T00:00",
  endDate: "2026-08-08T00:00",
  onStartDateChange: vi.fn(),
  onEndDateChange: vi.fn(),
  onQuickRange: vi.fn(),
};

afterEach(cleanup);

describe("TimeRangeSelector", () => {
  it("reveals custom dates on demand when collapsible", () => {
    render(<TimeRangeSelector {...props} collapsible />);

    expect(document.getElementById("custom-time-range")?.classList.contains("hidden")).toBe(true);

    fireEvent.click(screen.getByRole("button", { name: "Custom" }));

    expect(document.getElementById("custom-time-range")?.classList.contains("grid")).toBe(true);
    expect(screen.getByRole("button", { name: "Custom" }).getAttribute("aria-expanded")).toBe(
      "true",
    );
  });

  it("keeps custom dates visible by default for existing consumers", () => {
    render(<TimeRangeSelector {...props} />);

    expect(document.getElementById("custom-time-range")?.classList.contains("grid")).toBe(true);
  });
});

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

  it("opens custom dates initially when collapsible and no quick range matches", () => {
    render(
      <TimeRangeSelector
        {...props}
        startDate="2026-08-01T09:00"
        endDate="2026-08-05T18:00"
        collapsible
      />,
    );

    expect(document.getElementById("custom-time-range")?.classList.contains("grid")).toBe(true);
    expect(screen.getByRole("button", { name: "Custom" }).getAttribute("aria-expanded")).toBe(
      "true",
    );
  });

  it("keeps custom dates visible by default for existing consumers", () => {
    render(<TimeRangeSelector {...props} />);

    expect(document.getElementById("custom-time-range")?.classList.contains("grid")).toBe(true);
  });

  it("highlights the quick range button matching the exact span", () => {
    render(
      <TimeRangeSelector {...props} startDate="2026-08-01T00:00" endDate="2026-08-08T00:00" />,
    );

    const sevenDayButton = screen.getByRole("button", { name: "7D" });
    expect(sevenDayButton.getAttribute("aria-pressed")).toBe("true");
    expect(sevenDayButton.className).toContain("btn-primary");

    const oneDayButton = screen.getByRole("button", { name: "1D" });
    expect(oneDayButton.getAttribute("aria-pressed")).toBe("false");
    expect(oneDayButton.className).not.toContain("btn-primary");

    const thirtyDayButton = screen.getByRole("button", { name: "30D" });
    expect(thirtyDayButton.getAttribute("aria-pressed")).toBe("false");
  });

  it("highlights no quick range button when the span matches none of them", () => {
    render(
      <TimeRangeSelector {...props} startDate="2026-08-01T00:00" endDate="2026-08-03T00:00" />,
    );

    ["1D", "7D", "30D"].forEach((label) => {
      expect(screen.getByRole("button", { name: label }).getAttribute("aria-pressed")).toBe(
        "false",
      );
    });
  });

  it("highlights no quick range button when the dates are invalid or empty", () => {
    render(<TimeRangeSelector {...props} startDate="" endDate="" />);

    ["1D", "7D", "30D"].forEach((label) => {
      expect(screen.getByRole("button", { name: label }).getAttribute("aria-pressed")).toBe(
        "false",
      );
    });
  });
});

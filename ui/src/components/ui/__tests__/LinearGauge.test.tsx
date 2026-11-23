import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { LinearGauge } from "@/components/ui/LinearGauge";

afterEach(cleanup);

describe("LinearGauge", () => {
  it("shows measured coverage immediately and updates without intermediate values", () => {
    const { rerender } = render(
      <LinearGauge value={96} current={96} total={100} label="Coverage" />,
    );
    expect(screen.getByRole("progressbar", { name: "Coverage" })).toHaveAttribute("value", "96");
    expect(screen.getByText("96.0%")).toBeInTheDocument();
    expect(screen.getByText("Gold")).toBeInTheDocument();

    rerender(<LinearGauge value={20} current={20} total={100} label="Coverage" />);
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuetext", "20.0%, 20 of 100");
    expect(screen.getByText("20.0%")).toBeInTheDocument();
    expect(screen.queryByText("Gold")).not.toBeInTheDocument();
    expect(screen.getByText("80 to go")).toBeInTheDocument();
  });

  it("identifies missing data", () => {
    render(<LinearGauge value={0} current={0} total={64} />);
    expect(screen.getByText("No data")).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("value", "0");
  });

  it.each([
    [120, "100"],
    [-10, "0"],
    [NaN, "0"],
  ])("bounds invalid coverage %s", (value, expected) => {
    render(<LinearGauge value={value} current={0} total={100} />);
    expect(screen.getByRole("progressbar")).toHaveAttribute("value", expected);
  });
});

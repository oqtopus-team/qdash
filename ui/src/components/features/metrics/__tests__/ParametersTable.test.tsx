import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { ParametersTable } from "../ParametersTable";

describe("ParametersTable", () => {
  afterEach(() => cleanup());

  it("shows the previous database value beside a persisted execution result", () => {
    render(
      <ParametersTable
        title="Output Parameters"
        parameters={{
          readout_frequency: {
            value: 6.123,
            unit: "GHz",
            previous_database_value: 5.987,
            database_updated: true,
          },
        }}
      />,
    );

    expect(screen.getByText("Previous")).toBeTruthy();
    expect(screen.getByText("New")).toBeTruthy();
    expect(screen.getByText("5.987000")).toBeTruthy();
    expect(screen.getByText("6.123000")).toBeTruthy();
    expect(screen.getByText("Calibration DB updated")).toBeTruthy();
  });

  it("labels a result that was recorded without updating the database", () => {
    render(
      <ParametersTable
        title="Output Parameters"
        parameters={{
          readout_frequency: { value: 6.123, unit: "GHz", database_updated: false },
        }}
      />,
    );

    expect(screen.getByText("Value")).toBeTruthy();
    expect(screen.queryByText("Previous")).toBeNull();
    expect(screen.getByText("Measurement only")).toBeTruthy();
  });

  it("labels a legacy result without update metadata as unknown", () => {
    render(
      <ParametersTable
        title="Output Parameters"
        parameters={{ readout_frequency: { value: 6.123, unit: "GHz" } }}
      />,
    );

    expect(screen.getByText("Update status unknown")).toBeTruthy();
  });
});

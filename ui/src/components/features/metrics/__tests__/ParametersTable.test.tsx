import { cleanup, render, screen, within } from "@testing-library/react";
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
          readout_frequency: {
            value: 6.123,
            unit: "GHz",
            database_updated: false,
            database_updates: [
              {
                parameter_name: "readout_frequency",
                updated_value: 6.123,
                updated: false,
              },
            ],
          },
        }}
      />,
    );

    expect(screen.getByText("Value")).toBeTruthy();
    expect(screen.queryByText("Previous")).toBeNull();
    expect(screen.getByText("Measurement only")).toBeTruthy();
    const destinations = screen.getByLabelText("Database destinations for readout_frequency");
    expect(within(destinations).getByText("Not applied to calibration database:")).toBeTruthy();
    expect(within(destinations).getByText("readout_frequency")).toBeTruthy();
  });

  it("shows every database publish target for one output", () => {
    render(
      <ParametersTable
        title="Output Parameters"
        parameters={{
          qubit_frequency: {
            value: 5.2,
            unit: "GHz",
            previous_database_value: 5.1,
            database_updated: true,
            database_updates: [
              {
                parameter_name: "qubit_frequency",
                previous_value: 5.1,
                updated_value: 5.2,
                updated: true,
              },
              {
                parameter_name: "control_frequency",
                previous_value: 5.0,
                updated_value: 5.2,
                updated: true,
              },
            ],
          },
        }}
      />,
    );

    const destinations = screen.getByLabelText("Database destinations for qubit_frequency");
    expect(within(destinations).getByText("Applied to calibration database:")).toBeTruthy();
    expect(within(destinations).getByText("qubit_frequency")).toBeTruthy();
    expect(within(destinations).getByText("control_frequency")).toBeTruthy();
    expect(within(destinations).queryByText("5.000000 → 5.200000")).toBeNull();
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

  it("collapses parameter groups declared by persisted UI metadata", () => {
    render(
      <ParametersTable
        title="Input Parameters"
        parameters={{
          qubit_frequency: { value: 5.1, unit: "GHz" },
          normalization_reference: { value: 0.25, unit: "a.u." },
        }}
        parameterDefinitions={{
          normalization_reference: {
            ui_group: "Normalization context",
            ui_group_collapsed: true,
          },
        }}
      />,
    );

    expect(screen.getByText("qubit_frequency")).toBeTruthy();
    const group = screen.getByText("Normalization context").closest("details");
    expect(group).not.toBeNull();
    expect(group).not.toHaveAttribute("open");
    expect(within(group as HTMLElement).getByText("normalization_reference")).toBeTruthy();
  });
});

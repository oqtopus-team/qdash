import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SeedParametersPanel } from "../SeedParametersPanel";

const mutate = vi.fn();
const refetchComparison = vi.fn().mockResolvedValue(undefined);
const refetchQubits = vi.fn().mockResolvedValue(undefined);

vi.mock("@/components/selectors/ChipSelector", () => ({
  ChipSelector: ({
    selectedChip,
    onChipSelect,
  }: {
    selectedChip: string;
    onChipSelect: (chipId: string) => void;
  }) => (
    <button type="button" data-selected-chip={selectedChip} onClick={() => onChipSelect("chip-1")}>
      Choose chip
    </button>
  ),
}));

vi.mock("@/client/calibration/calibration", () => ({
  useCompareSeedValues: () => ({
    data: {
      data: {
        chip_id: "chip-1",
        parameters: {
          readout_frequency: {
            unit: "GHz",
            qubits: {
              "0": {
                yaml_qid: "Q00",
                yaml_value: 5.1,
                qdash_value: 5,
                status: "different",
              },
              "1": {
                yaml_qid: "Q01",
                yaml_value: 5.2,
                qdash_value: 5.2,
                status: "same",
              },
              "2": {
                yaml_qid: "Q02",
                yaml_value: 5.1234561,
                qdash_value: 5.1234564,
                status: "different",
              },
              "3": {
                yaml_qid: "Q03",
                yaml_value: 10.0005,
                qdash_value: null,
                status: "new",
              },
            },
          },
        },
      },
    },
    isLoading: false,
    isError: false,
    isRefetching: false,
    refetch: refetchComparison,
  }),
  useImportSeedParameters: () => ({
    mutate,
    isPending: false,
    isSuccess: false,
    isError: false,
  }),
}));

vi.mock("@/client/chip/chip", () => ({
  useListChips: () => ({
    data: {
      data: {
        chips: [
          {
            chip_id: "inactive-newer",
            installed_at: "2026-08-20T00:00:00Z",
            activity_status: "inactive",
          },
          {
            chip_id: "chip-1",
            installed_at: "2026-08-10T00:00:00Z",
            activity_status: "active",
          },
          {
            chip_id: "active-older",
            installed_at: "2026-08-01T00:00:00Z",
            activity_status: "active",
          },
        ],
      },
    },
  }),
  useListChipQubits: () => ({
    data: {
      data: {
        qubits: [
          {
            qid: "0",
            data: {
              readout_frequency: { value: 5, unit: "GHz" },
              coherence_time: { value: 42, unit: "us" },
            },
          },
          { qid: "1", data: { readout_frequency: { value: 5.2, unit: "GHz" } } },
          { qid: "2", data: { readout_frequency: { value: 5.1234564, unit: "GHz" } } },
          { qid: "3", data: { readout_frequency: { value: 10.0005, unit: "GHz" } } },
        ],
      },
    },
    isLoading: false,
    isError: false,
    refetch: refetchQubits,
  }),
}));

afterEach(() => {
  cleanup();
  mutate.mockReset();
  refetchComparison.mockClear();
  refetchQubits.mockClear();
});

describe("SeedParametersPanel", () => {
  it("selects the latest active chip by default", async () => {
    render(<SeedParametersPanel />);

    await waitFor(() => {
      expect(
        screen.getByRole("button", { name: "Choose chip" }).getAttribute("data-selected-chip"),
      ).toBe("chip-1");
    });
  });

  it("shows current calibration values even when they have no YAML candidate", () => {
    render(<SeedParametersPanel />);

    fireEvent.click(screen.getByRole("button", { name: "Choose chip" }));

    expect(screen.getByText("coherence_time")).toBeTruthy();
    fireEvent.click(screen.getByText("coherence_time"));
    expect(screen.getByText("42.0000")).toBeTruthy();
    expect(screen.getByText("Current")).toBeTruthy();
  });

  it("shows enough precision to explain a diff status", () => {
    render(<SeedParametersPanel />);

    fireEvent.click(screen.getByRole("button", { name: "Choose chip" }));
    fireEvent.click(screen.getByText("readout_frequency"));

    expect(screen.getByText("5.123456100")).toBeTruthy();
    expect(screen.getByText("5.123456400")).toBeTruthy();
  });

  it("recomputes a stale new status when the current value is available", () => {
    render(<SeedParametersPanel />);

    fireEvent.click(screen.getByRole("button", { name: "Choose chip" }));
    fireEvent.click(screen.getByText("readout_frequency"));

    const row = screen.getByText("Q03").closest("tr");
    expect(row).not.toBeNull();
    expect(within(row as HTMLTableRowElement).getByText("Same")).toBeTruthy();
    expect(within(row as HTMLTableRowElement).queryByText("New")).toBeNull();
  });

  it("edits an incoming value and selects it for import", () => {
    render(<SeedParametersPanel />);

    fireEvent.click(screen.getByRole("button", { name: "Choose chip" }));
    fireEvent.click(screen.getByText("readout_frequency"));
    expect(screen.getByText("Q00")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "Edit readout_frequency for qubit 0" }));

    const input = screen.getByRole("textbox", {
      name: "Proposed value for readout_frequency, qubit 0",
    });
    fireEvent.change(input, { target: { value: "5.15" } });
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    expect(screen.getByText("5.100000000")).toBeTruthy();
    expect(screen.getByText("5.15000")).toBeTruthy();
    expect(screen.getAllByText("Edited").length).toBeGreaterThan(0);
    expect(
      screen.getByRole("checkbox", { name: "Select readout_frequency for qubit 0" }),
    ).toHaveProperty("checked", true);
  });

  it("allows editing a same value and resets it to a non-importable row", () => {
    render(<SeedParametersPanel />);

    fireEvent.click(screen.getByRole("button", { name: "Choose chip" }));
    fireEvent.change(screen.getByLabelText("Show"), { target: { value: "all" } });
    fireEvent.click(screen.getByText("readout_frequency"));
    fireEvent.click(screen.getByRole("button", { name: "Edit readout_frequency for qubit 1" }));
    fireEvent.change(
      screen.getByRole("textbox", { name: "Proposed value for readout_frequency, qubit 1" }),
      { target: { value: "5.25" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Save" }));

    const checkbox = screen.getByRole("checkbox", {
      name: "Select readout_frequency for qubit 1",
    });
    expect(checkbox).toHaveProperty("checked", true);
    expect(checkbox).toHaveProperty("disabled", false);

    fireEvent.click(
      screen.getByRole("button", {
        name: "Reset readout_frequency for qubit 1 to YAML value",
      }),
    );

    expect(checkbox).toHaveProperty("checked", false);
    expect(checkbox).toHaveProperty("disabled", true);
  });

  it("reviews the exact values before importing", async () => {
    render(<SeedParametersPanel />);

    fireEvent.click(screen.getByRole("button", { name: "Choose chip" }));
    fireEvent.pointerDown(screen.getByRole("button", { name: /Import from YAML/ }));
    fireEvent.click(await screen.findByRole("menuitem", { name: "Review all YAML changes (2)" }));

    expect(screen.getByText("Review calibration updates")).toBeTruthy();
    expect(screen.getByText("5.00000")).toBeTruthy();
    expect(screen.getByText(/5.10000 GHz/)).toBeTruthy();

    fireEvent.click(screen.getByRole("button", { name: "Apply 2 values" }));

    expect(mutate).toHaveBeenCalledWith(
      {
        data: {
          chip_id: "chip-1",
          source: "manual",
          manual_data: {
            readout_frequency: {
              "0": { value: 5.1, unit: "GHz" },
              "2": { value: 5.1234561, unit: "GHz" },
            },
          },
        },
      },
      expect.any(Object),
    );

    const mutationOptions = mutate.mock.calls[0]?.[1] as { onSuccess: () => Promise<void> };
    await mutationOptions.onSuccess();
    expect(refetchComparison).toHaveBeenCalledOnce();
    expect(refetchQubits).toHaveBeenCalledOnce();
  });

  it("cancels an edit without changing or selecting the value", () => {
    render(<SeedParametersPanel />);

    fireEvent.click(screen.getByRole("button", { name: "Choose chip" }));
    fireEvent.click(screen.getByText("readout_frequency"));
    fireEvent.click(screen.getByRole("button", { name: "Edit readout_frequency for qubit 0" }));
    fireEvent.change(
      screen.getByRole("textbox", { name: "Proposed value for readout_frequency, qubit 0" }),
      { target: { value: "9.99" } },
    );
    fireEvent.click(screen.getByRole("button", { name: "Cancel" }));

    expect(screen.queryByText("9.99000")).toBeNull();
    expect(
      screen.getByRole("checkbox", { name: "Select readout_frequency for qubit 0" }),
    ).toHaveProperty("checked", false);
  });
});

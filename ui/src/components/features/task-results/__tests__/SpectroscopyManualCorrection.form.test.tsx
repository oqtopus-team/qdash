import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { SpectroscopyManualCorrection } from "@/components/features/task-results/SpectroscopyManualCorrection";

const mocks = vi.hoisted(() => ({
  mutate: vi.fn(),
  invalidateQueries: vi.fn(),
  qubitData: {} as Record<string, unknown>,
  state: { isPending: false, isError: false, error: null as unknown },
}));

vi.mock("@tanstack/react-query", () => ({
  useQueryClient: () => ({ invalidateQueries: mocks.invalidateQueries }),
}));

vi.mock("@/client/calibration/calibration", () => ({
  useUpdateCalibrationParameters: () => ({ mutate: mocks.mutate, ...mocks.state }),
}));

vi.mock("@/client/chip/chip", () => ({
  getGetChipQubitQueryKey: (chipId: string, qid: string) => ["qubit", chipId, qid],
  useGetChipQubit: () => ({ data: { data: { data: mocks.qubitData } } }),
}));

vi.mock("@/client/task/task", () => ({
  getGetTaskResultQueryKey: (taskId: string) => ["task-result", taskId],
}));

vi.mock("@/components/charts/PlotlyRenderer", () => ({
  PlotlyRenderer: ({ onClick }: { onClick: (event: unknown) => void }) => (
    <button type="button" onClick={() => onClick({ points: [{ x: 10.25, y: -20 }] })}>
      Plot point
    </button>
  ),
}));

vi.mock("@/components/features/task-results/CalibrationGitHubSyncNotice", () => ({
  CalibrationGitHubSyncNotice: ({ result }: { result: { task_id: string } }) => (
    <div data-testid="github-result">{result.task_id}</div>
  ),
}));

/** Renders the correction card for a resonator spectroscopy result and opens the form. */
function openForm(jsonFigurePaths: string[] = ["fig.json"]) {
  render(
    <SpectroscopyManualCorrection
      chipId="chip-1"
      qid="Q00"
      taskId="task-1"
      taskName="CheckResonatorSpectroscopy"
      outputParameters={{
        resonator_frequency: { value: 10.1, unit: "GHz" },
        readout_amplitude: { value: 0.2, unit: "a.u." },
      }}
      jsonFigurePaths={jsonFigurePaths}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: /Correct values/ }));
}

/** Returns the correction input for a parameter. */
function field(name: string) {
  return screen.getByLabelText(`Correct ${name}`) as HTMLInputElement;
}

/** Returns the button that opens the confirmation step. */
function reviewButton() {
  return screen.getByRole("button", { name: "Review changes" });
}

afterEach(() => {
  cleanup();
  mocks.mutate.mockReset();
  mocks.invalidateQueries.mockReset();
  mocks.qubitData = {};
  mocks.state.isError = false;
  mocks.state.error = null;
});

describe("SpectroscopyManualCorrection form", () => {
  it("starts from the current DB values and requires a change", async () => {
    mocks.qubitData = { readout_frequency: { value: 10.2, unit: "GHz" } };
    openForm();

    expect(field("readout_frequency").value).toBe("10.2");
    expect(field("readout_amplitude").value).toBe("0.2");
    expect(screen.getByText("Change one or more values to continue.")).toBeTruthy();
    expect(reviewButton()).toBeDisabled();

    fireEvent.change(field("readout_frequency"), { target: { value: "10.3" } });
    await waitFor(() => expect(reviewButton()).toBeEnabled());
    fireEvent.change(field("readout_frequency"), { target: { value: "10.20" } });
    await waitFor(() => expect(reviewButton()).toBeDisabled());
    expect(screen.getByText("Change one or more values to continue.")).toBeTruthy();
  });

  it("shows an invalid number next to its field and blocks review", async () => {
    openForm();
    const input = field("readout_frequency");

    fireEvent.change(input, { target: { value: "abc" } });

    const error = await screen.findByText("Enter a finite number");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAttribute("aria-describedby", error.id);
    expect(reviewButton()).toBeDisabled();

    fireEvent.change(input, { target: { value: "" } });
    await waitFor(() => expect(input).toHaveAttribute("aria-invalid", "true"));

    fireEvent.change(input, { target: { value: "10.3" } });
    await waitFor(() => expect(input).toHaveAttribute("aria-invalid", "false"));
    expect(input).not.toHaveAttribute("aria-describedby");
    await waitFor(() => expect(reviewButton()).toBeEnabled());
  });

  it("resets a changed field to its baseline", async () => {
    openForm();
    fireEvent.change(field("readout_amplitude"), { target: { value: "0.5" } });
    await waitFor(() => expect(reviewButton()).toBeEnabled());

    fireEvent.click(screen.getByTitle("Reset"));

    await waitFor(() => expect(field("readout_amplitude").value).toBe("0.2"));
    await waitFor(() => expect(reviewButton()).toBeDisabled());
  });

  it("applies a picked chart point to the form", async () => {
    openForm();
    fireEvent.click(screen.getByRole("button", { name: /Pick x\/y from plot/ }));
    fireEvent.click(screen.getByRole("button", { name: "Plot point" }));
    fireEvent.click(screen.getByRole("button", { name: "Use selected point" }));

    await waitFor(() => expect(field("readout_frequency").value).toBe("10.25"));
    expect(field("readout_amplitude").value).toBe(String(10 ** (-20 / 20)));
    expect(screen.getByText("2 values will be updated.")).toBeTruthy();
    await waitFor(() => expect(reviewButton()).toBeEnabled());

    fireEvent.click(reviewButton());
    fireEvent.click(
      within(await screen.findByRole("dialog")).getByRole("button", { name: "Update DB" }),
    );
    expect(mocks.mutate.mock.calls[0][0].data).toMatchObject({
      correction_point: { x: 10.25, y: -20 },
      parameters: {
        readout_frequency: { value: 10.25, unit: "GHz" },
        readout_amplitude: { value: 10 ** (-20 / 20), unit: "a.u." },
      },
    });
  });

  it("saves only the changed values after confirmation", async () => {
    mocks.mutate.mockImplementation((_variables, options) =>
      options.onSuccess({ data: { task_id: "task-2" } }),
    );
    openForm();
    fireEvent.change(field("readout_frequency"), { target: { value: " 10.3 " } });
    await waitFor(() => expect(reviewButton()).toBeEnabled());

    fireEvent.click(reviewButton());
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByText("readout_frequency")).toBeTruthy();
    expect(within(dialog).queryByText("readout_amplitude")).toBeNull();
    expect(within(dialog).getByText("10.3 GHz")).toBeTruthy();
    fireEvent.click(within(dialog).getByRole("button", { name: "Update DB" }));

    expect(mocks.mutate).toHaveBeenCalledTimes(1);
    expect(mocks.mutate.mock.calls[0][0]).toEqual({
      data: {
        chip_id: "chip-1",
        qid: "Q00",
        source_task_id: "task-1",
        correction_point: undefined,
        parameters: { readout_frequency: { value: 10.3, unit: "GHz" } },
      },
    });
    expect(await screen.findByText("Manual correction saved.")).toBeTruthy();
    expect(screen.getByRole("link", { name: "View correction result" })).toHaveAttribute(
      "href",
      "/task-results/task-2",
    );
    expect(screen.getByTestId("github-result")).toHaveTextContent("task-2");
    expect(mocks.invalidateQueries).toHaveBeenCalledWith({ queryKey: ["qubit", "chip-1", "Q00"] });
    expect(mocks.invalidateQueries).toHaveBeenCalledWith({ queryKey: ["task-result", "task-1"] });
  });

  it("shows a server error separately from field errors", async () => {
    mocks.state.isError = true;
    mocks.state.error = new Error("Server rejected the value");
    openForm();

    expect(screen.getByText(/Correction failed: Server rejected the value/)).toBeTruthy();
  });
});

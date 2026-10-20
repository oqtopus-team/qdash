import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ReanalysisPanel } from "@/components/features/qubit/ReanalysisPanel";

const mocks = vi.hoisted(() => ({
  mutate: vi.fn(),
  reset: vi.fn(),
  state: {
    isPending: false,
    isError: false,
    error: null as unknown,
    data: undefined,
  },
}));

vi.mock("next/dynamic", () => ({ default: () => () => null }));

vi.mock("@/client/chip/chip", () => {
  const useMutation = () => ({
    mutate: mocks.mutate,
    reset: mocks.reset,
    ...mocks.state,
  });
  return {
    useReanalyzeResonatorSpectroscopy: useMutation,
    useReanalyzeQubitSpectroscopy: useMutation,
  };
});

/** Renders the panel for the given task name. */
function renderPanel(taskName: string, sourceTaskId: string | null = "task-1") {
  return render(
    <ReanalysisPanel
      chipId="chip-1"
      qubitId="Q00"
      taskName={taskName}
      sourceTaskId={sourceTaskId}
    />,
  );
}

/** Sets the value of the field with the given label. */
function setField(label: string, value: string) {
  fireEvent.change(screen.getByLabelText(label), { target: { value } });
}

/** Sets a value that a number input would sanitize away (e.g. 1e999) by switching the input to text. */
function setNonFiniteField(label: string, value: string) {
  const input = screen.getByLabelText(label) as HTMLInputElement;
  input.type = "text";
  fireEvent.change(input, { target: { value } });
}

/** Clicks the Preview submit button. */
function submit() {
  fireEvent.click(screen.getByRole("button", { name: "Preview" }));
}

describe("ReanalysisPanel", () => {
  afterEach(() => {
    cleanup();
    mocks.mutate.mockReset();
    mocks.reset.mockReset();
    mocks.state.isError = false;
    mocks.state.error = null;
  });

  it("renders nothing for unsupported tasks", () => {
    const { container } = renderPanel("OtherTask");
    expect(container.firstChild).toBeNull();
  });

  describe("resonator form", () => {
    const TASK = "CheckResonatorSpectroscopy";

    it("submits nulls when every field is empty", async () => {
      renderPanel(TASK);
      submit();

      await waitFor(() => expect(mocks.mutate).toHaveBeenCalledTimes(1));
      expect(mocks.mutate).toHaveBeenCalledWith({
        chipId: "chip-1",
        qid: "Q00",
        data: {
          source_task_id: "task-1",
          parameters: {
            num_resonators: null,
            high_power_min: null,
            high_power_max: null,
            low_power: null,
            bare_shift_estimator_type: null,
            bare_shift_strength_limit: null,
          },
        },
      });
    });

    it("submits normalized numbers in manual mode", async () => {
      renderPanel(TASK, null);
      setField("num_resonators", "4");
      setField("bare_shift_estimator_type", "config");
      setField("high_power_min (dB)", "-20");
      setField("high_power_max (dB)", "0.5");
      setField("low_power (dB)", "-30");
      submit();

      await waitFor(() => expect(mocks.mutate).toHaveBeenCalledTimes(1));
      expect(mocks.mutate.mock.calls[0][0].data).toEqual({
        source_task_id: null,
        parameters: {
          num_resonators: 4,
          high_power_min: -20,
          high_power_max: 0.5,
          low_power: -30,
          bare_shift_estimator_type: "config",
          bare_shift_strength_limit: null,
        },
      });
    });

    it.each(["1.5", "0", "-2"])("rejects num_resonators=%s with a field error", async (value) => {
      renderPanel(TASK);
      setField("num_resonators", value);
      submit();

      const error = await screen.findByText("Must be a positive integer");
      const input = screen.getByLabelText("num_resonators");
      expect(input.getAttribute("aria-invalid")).toBe("true");
      expect(input.getAttribute("aria-describedby")).toBe(error.id);
      expect(input.className).toContain("input-error");
      expect(mocks.mutate).not.toHaveBeenCalled();
    });

    it("nulls and ignores disabled power fields in auto mode", async () => {
      renderPanel(TASK);
      setField("high_power_min (dB)", "-20");
      setField("low_power (dB)", "-30");
      setField("bare_shift_estimator_type", "high_frequency_strength");
      setField("bare_shift_strength_limit", "4");

      expect((screen.getByLabelText("high_power_min (dB)") as HTMLInputElement).disabled).toBe(
        true,
      );
      submit();

      await waitFor(() => expect(mocks.mutate).toHaveBeenCalledTimes(1));
      expect(mocks.mutate.mock.calls[0][0].data.parameters).toEqual({
        num_resonators: null,
        high_power_min: null,
        high_power_max: null,
        low_power: null,
        bare_shift_estimator_type: "high_frequency_strength",
        bare_shift_strength_limit: 4,
      });
    });

    it("nulls the strength limit in manual mode and keeps it in auto mode", async () => {
      renderPanel(TASK);
      setField("bare_shift_estimator_type", "high_frequency_strength");
      setField("bare_shift_strength_limit", "4");
      setField("bare_shift_estimator_type", "config");
      submit();

      await waitFor(() => expect(mocks.mutate).toHaveBeenCalledTimes(1));
      expect(mocks.mutate.mock.calls[0][0].data.parameters.bare_shift_strength_limit).toBeNull();

      setField("bare_shift_estimator_type", "high_frequency_strength");
      submit();

      await waitFor(() => expect(mocks.mutate).toHaveBeenCalledTimes(2));
      expect(mocks.mutate.mock.calls[1][0].data.parameters.bare_shift_strength_limit).toBe(4);
    });

    it("clears a stale power-field error when switching to auto mode", async () => {
      renderPanel(TASK);
      setNonFiniteField("low_power (dB)", "1e999");
      submit();

      const input = screen.getByLabelText("low_power (dB)");
      expect(await screen.findByText("Must be a number")).toBeTruthy();
      expect(input.getAttribute("aria-invalid")).toBe("true");

      setField("bare_shift_estimator_type", "high_frequency_strength");

      await waitFor(() => expect(screen.queryByText("Must be a number")).toBeNull());
      expect(input.getAttribute("aria-invalid")).toBe("false");
    });

    it("renders a mutation error separately from field errors", async () => {
      mocks.state.isError = true;
      mocks.state.error = new Error("boom");
      renderPanel(TASK);

      expect(screen.getByText("Reanalysis failed: boom")).toBeTruthy();
      expect(screen.queryByText("Must be a positive integer")).toBeNull();
      expect(screen.getByLabelText("num_resonators").getAttribute("aria-invalid")).toBe("false");
    });

    it("clears values and the mutation on reset", async () => {
      renderPanel(TASK);
      setField("num_resonators", "3");
      fireEvent.click(screen.getByRole("button", { name: "Reset" }));

      await waitFor(() =>
        expect((screen.getByLabelText("num_resonators") as HTMLInputElement).value).toBe(""),
      );
      expect(mocks.reset).toHaveBeenCalledTimes(1);
    });

    it("keeps ids unique when rendered twice", () => {
      render(
        <>
          <ReanalysisPanel chipId="c" qubitId="Q00" taskName={TASK} />
          <ReanalysisPanel chipId="c" qubitId="Q01" taskName={TASK} />
        </>,
      );
      const inputs = screen.getAllByLabelText("num_resonators");
      expect(inputs).toHaveLength(2);
      expect(inputs[0].id).not.toBe(inputs[1].id);
    });
  });

  describe("qubit form", () => {
    const TASK = "CheckQubitSpectroscopy";

    it("submits nulls and retry_with_trim=null by default", async () => {
      renderPanel(TASK);
      submit();

      await waitFor(() => expect(mocks.mutate).toHaveBeenCalledTimes(1));
      expect(mocks.mutate.mock.calls[0][0].data.parameters).toEqual({
        binarize_threshold_sigma_plus: null,
        binarize_threshold_sigma_minus: null,
        top_power: null,
        f01_height_min: null,
        f12_distance_min: null,
        f12_distance_max: null,
        f12_height_min: null,
        retry_with_trim: null,
      });
    });

    it("submits parsed numbers and retry_with_trim=true", async () => {
      renderPanel(TASK);
      setField("binarize_threshold_sigma_plus", "3.5");
      setField("binarize_threshold_sigma_minus", "-2");
      setField("f12_distance_min (GHz)", "0.125");
      fireEvent.click(screen.getByLabelText("retry_with_trim"));
      submit();

      await waitFor(() => expect(mocks.mutate).toHaveBeenCalledTimes(1));
      expect(mocks.mutate.mock.calls[0][0].data.parameters).toEqual({
        binarize_threshold_sigma_plus: 3.5,
        binarize_threshold_sigma_minus: -2,
        top_power: null,
        f01_height_min: null,
        f12_distance_min: 0.125,
        f12_distance_max: null,
        f12_height_min: null,
        retry_with_trim: true,
      });
    });

    it("rejects a non-finite number with a field error", async () => {
      renderPanel(TASK);
      setNonFiniteField("top_power (dB)", "1e999");
      submit();

      const error = await screen.findByText("Must be a number");
      const input = screen.getByLabelText("top_power (dB)");
      expect(input.getAttribute("aria-invalid")).toBe("true");
      expect(input.getAttribute("aria-describedby")).toBe(error.id);
      expect(mocks.mutate).not.toHaveBeenCalled();
    });

    it("renders a mutation error without field errors", () => {
      mocks.state.isError = true;
      mocks.state.error = new Error("server down");
      renderPanel(TASK);

      expect(screen.getByText("Reanalysis failed: server down")).toBeTruthy();
      expect(screen.queryByText("Must be a number")).toBeNull();
    });
  });
});

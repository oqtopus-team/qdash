import { act, cleanup, render, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FirstCalibrationCoachmarks } from "@/components/features/first-calibration/FirstCalibrationCoachmarks";

import { storeJourney, storedJourney } from "./journeyTestUtils";

interface FakePopover {
  wrapper: HTMLElement;
  title: HTMLElement;
  description: HTMLElement;
  closeButton: HTMLButtonElement;
  nextButton: HTMLButtonElement;
}

interface HighlightStep {
  element: HTMLElement;
  popover: {
    title: string;
    description: string;
    showButtons: string[];
    progressText: string;
    onNextClick: () => void;
    onCloseClick: () => void;
  };
}

interface FakeDriver {
  config: { overlayOpacity: number; allowKeyboardControl: boolean };
  step: HighlightStep | null;
  destroyed: boolean;
  highlight: (step: HighlightStep) => void;
  destroy: () => void;
  refresh: () => void;
}

const mocks = vi.hoisted(() => ({
  pathname: "/chip",
  search: "",
  projectId: "project-1",
  canEdit: true,
  drivers: [] as FakeDriver[],
  toastInfo: vi.fn(),
  /** The journey's execution as the server answers it; undefined while it loads. */
  execution: undefined as unknown,
}));

vi.mock("driver.js", () => ({
  driver: (
    config: FakeDriver["config"] & {
      onPopoverRender?: (popover: FakePopover) => void;
    },
  ) => {
    const instance: FakeDriver = {
      config,
      step: null,
      destroyed: false,
      highlight(step) {
        instance.step = step;
        const wrapper = document.createElement("div");
        wrapper.className = "driver-popover";
        const make = <T extends HTMLElement>(tag: string) => {
          const element = document.createElement(tag) as T;
          wrapper.appendChild(element);
          return element;
        };
        const popover: FakePopover = {
          wrapper,
          title: make("div"),
          description: make("div"),
          closeButton: make<HTMLButtonElement>("button"),
          nextButton: make<HTMLButtonElement>("button"),
        };
        popover.title.textContent = step.popover.title;
        popover.description.textContent = step.popover.description;
        document.body.appendChild(wrapper);
        config.onPopoverRender?.(popover);
        // Like driver.js, move focus into the popover right after rendering it.
        popover.closeButton.focus();
      },
      destroy() {
        instance.destroyed = true;
        document.querySelectorAll(".driver-popover").forEach((node) => node.remove());
      },
      refresh: vi.fn(),
    };
    mocks.drivers.push(instance);
    return instance;
  },
}));

vi.mock("next/navigation", () => ({
  usePathname: () => mocks.pathname,
  useSearchParams: () => new URLSearchParams(mocks.search),
}));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ username: "alice" }),
}));

vi.mock("@/contexts/ProjectContext", () => ({
  useProject: () => ({ projectId: mocks.projectId, canEdit: mocks.canEdit }),
}));

vi.mock("@/components/ui/Toast", () => ({
  useToast: () => ({ info: mocks.toastInfo }),
}));

vi.mock("@/client/chip/chip", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  useListChips: () => ({
    data: { data: { chips: [{ chip_id: "chip-a", size: 64 }] } },
    isError: false,
    isFetching: false,
    refetch: vi.fn(),
  }),
  useListChipConfigSources: () => ({
    data: {
      data: {
        available: true,
        sources: [],
        deployment_backend: "fake",
        presets: [
          {
            preset_id: "fake",
            n_qubits: 64,
            mux_count: 16,
            topology_id: "square-lattice-mux-64",
            workflow_template_id: "fake_calibration",
          },
        ],
      },
    },
    isError: false,
    refetch: vi.fn(),
  }),
}));

vi.mock("@/client/flow/flow", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  useGetFlow: () => ({
    data: { data: { name: "first_calibration", chip_id: "chip-a" } },
    isLoading: false,
    isError: false,
    error: null,
  }),
}));

vi.mock("@/client/execution/execution", async (importOriginal) => ({
  ...(await importOriginal<object>()),
  useGetExecution: () =>
    mocks.execution === undefined
      ? { data: undefined, isLoading: true, isError: false, error: null }
      : { data: { data: mocks.execution }, isLoading: false, isError: false, error: null },
}));

function mount(html: string): void {
  const container = document.createElement("div");
  container.dataset.testPage = "true";
  container.innerHTML = html;
  document.body.appendChild(container);
}

function unmountPage(): void {
  document.querySelectorAll("[data-test-page]").forEach((node) => node.remove());
}

function live() {
  return mocks.drivers.filter((instance) => !instance.destroyed && instance.step);
}

function shown(): HighlightStep {
  const active = live();
  expect(active).toHaveLength(1);
  return active[0].step as HighlightStep;
}

describe("FirstCalibrationCoachmarks", () => {
  beforeEach(() => {
    mocks.pathname = "/chip";
    mocks.search = "";
    mocks.projectId = "project-1";
    mocks.canEdit = true;
    mocks.drivers = [];
    mocks.execution = undefined;
    vi.spyOn(Element.prototype, "getClientRects").mockImplementation(
      () => [{ width: 10, height: 10 }] as unknown as DOMRectList,
    );
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    mocks.toastInfo.mockReset();
    document.body.innerHTML = "";
    window.localStorage.clear();
  });

  it("shows nothing without an active journey, or to a viewer", async () => {
    mount('<button data-coachmark="create-chip">Create Chip</button>');
    const { rerender } = render(<FirstCalibrationCoachmarks />);
    await act(async () => {});
    expect(mocks.drivers).toHaveLength(0);

    storeJourney("project-1");
    mocks.canEdit = false;
    rerender(<FirstCalibrationCoachmarks />);
    await act(async () => {});
    expect(mocks.drivers).toHaveLength(0);
  });

  it("waits for the target, then follows the page into the Create Chip dialog", async () => {
    storeJourney("project-1");
    render(<FirstCalibrationCoachmarks />);
    await act(async () => {});
    expect(live()).toHaveLength(0);

    mount('<button data-coachmark="create-chip">Create Chip</button>');
    await waitFor(() => expect(shown().popover.title).toBe("Open the chip form"));
    const opener = shown();
    // An action step cannot be skipped with Next; only the real action moves it.
    expect(opener.popover.showButtons).toEqual(["close"]);
    expect(opener.element.classList.contains("qdash-coachmark-target")).toBe(true);

    mount(
      '<div role="dialog"><input id="chip-id-input" /><button data-coachmark="create-chip-submit">Create Chip</button></div>',
    );
    await waitFor(() => expect(shown().popover.title).toBe("Name the chip"));
    expect(opener.element.classList.contains("qdash-coachmark-target")).toBe(false);
    // Steps inside a dialog never dim the page on top of it.
    expect(live()[0].config.overlayOpacity).toBe(0);
    expect(live()[0].config.allowKeyboardControl).toBe(false);
  });

  it("keeps focus in the field the user is typing in", async () => {
    storeJourney("project-1");
    mount(
      '<input id="chip-id-input" /><button data-coachmark="create-chip-submit">Create</button>',
    );
    const input = document.getElementById("chip-id-input") as HTMLInputElement;
    input.focus();
    render(<FirstCalibrationCoachmarks />);
    await waitFor(() => expect(shown().popover.title).toBe("Name the chip"));
    await act(async () => {});
    expect(document.activeElement).toBe(input);
  });

  it("moves through explanations with Next and stops at the action that saves", async () => {
    storeJourney("project-1", { chipId: "chip-a" });
    mocks.pathname = "/workflow/new";
    mocks.search = "journey=first-calibration";
    mount(
      '<div data-coachmark="flow-template" data-coachmark-ready="true"></div><input data-coachmark="flow-name" /><button data-coachmark="flow-save">Save Flow</button>',
    );
    render(<FirstCalibrationCoachmarks />);
    await waitFor(() => expect(shown().popover.title).toBe("Review the calibration"));
    expect(shown().popover.showButtons).toEqual(["next", "close"]);

    act(() => shown().popover.onNextClick());
    await waitFor(() => expect(shown().popover.title).toBe("Name the flow"));
    act(() => shown().popover.onNextClick());
    await waitFor(() => expect(shown().popover.title).toBe("Save the flow"));
    expect(shown().popover.showButtons).toEqual(["close"]);
    // Reading the explanations never moves the journey itself.
    expect(storedJourney("project-1")).toMatchObject({
      chipId: "chip-a",
      flowName: null,
    });
  });

  it("waits for the template to load before explaining it", async () => {
    storeJourney("project-1", { chipId: "chip-a" });
    mocks.pathname = "/workflow/new";
    mocks.search = "journey=first-calibration";
    mount(
      '<div id="template" data-coachmark="flow-template"></div><button data-coachmark="flow-save">Save Flow</button>',
    );
    render(<FirstCalibrationCoachmarks />);
    await act(async () => {});
    expect(live()).toHaveLength(0);

    document.getElementById("template")?.setAttribute("data-coachmark-ready", "true");
    await waitFor(() => expect(shown().popover.title).toBe("Review the calibration"));
  });

  it("pauses the journey when closed, so Home can resume it", async () => {
    storeJourney("project-1");
    mount('<button data-coachmark="create-chip">Create Chip</button>');
    render(<FirstCalibrationCoachmarks />);
    await waitFor(() => expect(shown().popover.title).toBe("Open the chip form"));

    act(() => shown().popover.onCloseClick());
    await waitFor(() => expect(live()).toHaveLength(0));
    expect(storedJourney("project-1")).toMatchObject({ status: "paused" });
    expect(mocks.toastInfo).toHaveBeenCalledWith("Guide paused. Resume it from Home.");
    expect(document.querySelector(".qdash-coachmark-target")).toBeNull();
  });

  it("cleans up on route changes, missing targets and unmount", async () => {
    storeJourney("project-1");
    mount('<button data-coachmark="create-chip">Create Chip</button>');
    const { rerender, unmount } = render(<FirstCalibrationCoachmarks />);
    await waitFor(() => expect(shown().popover.title).toBe("Open the chip form"));

    // The page goes away with the route; the old highlight must not linger.
    mocks.pathname = "/metrics";
    unmountPage();
    rerender(<FirstCalibrationCoachmarks />);
    await waitFor(() => expect(live()).toHaveLength(0));
    expect(document.querySelector(".driver-popover")).toBeNull();

    mount('<a data-coachmark="journey-action" href="/chip?journey=create-chip">Create a chip</a>');
    await waitFor(() => expect(shown().popover.title).toBe("Create a chip"));
    unmount();
    expect(live()).toHaveLength(0);
    expect(document.querySelector(".qdash-coachmark-target")).toBeNull();
  });

  it("follows the journey of the current project only", async () => {
    storeJourney("project-1");
    mount('<button data-coachmark="create-chip">Create Chip</button>');
    const { rerender } = render(<FirstCalibrationCoachmarks />);
    await waitFor(() => expect(shown().popover.title).toBe("Open the chip form"));

    mocks.projectId = "project-2";
    rerender(<FirstCalibrationCoachmarks />);
    await waitFor(() => expect(live()).toHaveLength(0));
  });

  it("leaves Tab to the page instead of trapping it in the popover", async () => {
    storeJourney("project-1");
    mount('<button data-coachmark="create-chip">Create Chip</button>');
    render(<FirstCalibrationCoachmarks />);
    await waitFor(() => expect(shown().popover.title).toBe("Open the chip form"));

    // driver.js listens for Tab on window; the page's own handlers still see the key.
    const onWindow = vi.fn();
    const onPage = vi.fn();
    window.addEventListener("keydown", onWindow);
    document.body.addEventListener("keydown", onPage);
    document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "Tab", bubbles: true }));
    document.body.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true }));
    window.removeEventListener("keydown", onWindow);
    document.body.removeEventListener("keydown", onPage);

    expect(onPage).toHaveBeenCalledTimes(2);
    expect(onWindow.mock.calls.map(([event]) => (event as KeyboardEvent).key)).toEqual(["Enter"]);
  });

  describe("result step", () => {
    const RAN = { chipId: "chip-a", flowName: "first_calibration", executionId: "exec-1" };
    // The recommended result's graph and values, and the control that closes its preview.
    const RESULT_VIEW =
      '<div data-coachmark="task-result-figure" data-task-id="t1"></div>' +
      '<div data-coachmark="task-result-metrics" data-task-id="t1"></div>';
    const PREVIEW = `${RESULT_VIEW}<button aria-label="Close task result preview">Close</button>`;

    beforeEach(() => {
      mocks.execution = {
        execution_id: "exec-1",
        chip_id: "chip-a",
        status: "completed",
        task: [
          { task_id: "t1", name: "CheckT1", status: "completed", qid: "0", figure_path: ["f"] },
        ],
      };
    });

    it("stays on Inspect a result while it explains the graph and values, then moves on", async () => {
      storeJourney("project-1", RAN);
      mocks.pathname = "/execution/chip-a/exec-1";
      mount(`<div class="react-flow__node" data-id="t1"></div>${PREVIEW}`);
      render(<FirstCalibrationCoachmarks />);

      await waitFor(() => expect(shown().popover.title).toBe("Read the graph"));
      expect(shown().popover.progressText).toBe("Step 4 of 5 · Inspect a result");
      expect(storedJourney("project-1").inspectedTaskId).toBeNull();

      act(() => shown().popover.onNextClick());
      await waitFor(() => expect(shown().popover.title).toBe("Check the fitted values"));
      expect(shown().popover.progressText).toBe("Step 4 of 5 · Inspect a result");
      expect(storedJourney("project-1").inspectedTaskId).toBeNull();

      // The explanation is over: the journey records the result and the guide moves on.
      act(() => shown().popover.onNextClick());
      await waitFor(() => expect(storedJourney("project-1").inspectedTaskId).toBe("t1"));
      await waitFor(() => expect(shown().popover.title).toBe("Close the preview"));
      expect(shown().popover.progressText).toBe("Step 5 of 5 · Chip overview");
    });

    it("explains the result on its own page, then points at the chip overview", async () => {
      storeJourney("project-1", RAN);
      mocks.pathname = "/task-results/t1";
      mount(`${RESULT_VIEW}<a data-coachmark="journey-action" href="/chip?chip=chip-a">Go</a>`);
      render(<FirstCalibrationCoachmarks />);

      await waitFor(() => expect(shown().popover.title).toBe("Read the graph"));
      act(() => shown().popover.onNextClick());
      await waitFor(() => expect(shown().popover.title).toBe("Check the fitted values"));
      act(() => shown().popover.onNextClick());
      await waitFor(() => expect(shown().popover.title).toBe("See the whole chip"));
      expect(shown().popover.progressText).toBe("Step 5 of 5 · Chip overview");
      expect(storedJourney("project-1").inspectedTaskId).toBe("t1");
    });

    it("does not count an unexplained result as inspected while it waits for the user", async () => {
      storeJourney("project-1", RAN);
      mocks.pathname = "/execution/chip-a/exec-1";
      mount('<div class="react-flow__node" data-id="t1"></div>');
      render(<FirstCalibrationCoachmarks />);

      await waitFor(() => expect(shown().popover.title).toBe("Open a result"));
      expect(shown().popover.progressText).toBe("Step 4 of 5 · Inspect a result");
      await act(async () => {});
      expect(storedJourney("project-1").inspectedTaskId).toBeNull();
    });

    it("resumes an exited explanation where it stopped, still on the result step", async () => {
      storeJourney("project-1", RAN);
      mocks.pathname = "/execution/chip-a/exec-1";
      mount(`<div class="react-flow__node" data-id="t1"></div>${PREVIEW}`);
      const { rerender } = render(<FirstCalibrationCoachmarks />);

      await waitFor(() => expect(shown().popover.title).toBe("Read the graph"));
      act(() => shown().popover.onNextClick());
      await waitFor(() => expect(shown().popover.title).toBe("Check the fitted values"));

      act(() => shown().popover.onCloseClick());
      await waitFor(() => expect(live()).toHaveLength(0));
      expect(storedJourney("project-1")).toMatchObject({ status: "paused", inspectedTaskId: null });

      // Home resumes the journey.
      storeJourney("project-1", RAN);
      act(() => {
        window.dispatchEvent(new StorageEvent("storage"));
      });
      rerender(<FirstCalibrationCoachmarks />);
      await waitFor(() => expect(shown().popover.title).toBe("Check the fitted values"));
      expect(shown().popover.progressText).toBe("Step 4 of 5 · Inspect a result");
      expect(storedJourney("project-1").inspectedTaskId).toBeNull();
    });
  });
});

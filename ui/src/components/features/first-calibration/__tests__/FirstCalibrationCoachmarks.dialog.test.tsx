import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { FirstCalibrationCoachmarks } from "@/components/features/first-calibration/FirstCalibrationCoachmarks";
import { Dialog, DialogContent, DialogTitle } from "@/components/ui/Dialog";

import { storeJourney, storedJourney } from "./journeyTestUtils";

// The real driver.js and the real Radix dialog: the guide has to work inside the dialog's focus
// trap, outside-click handling and aria-hidden scope, not only against a stand-in.

const mocks = vi.hoisted(() => ({
  pathname: "/chip",
  search: "",
  toastInfo: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  usePathname: () => mocks.pathname,
  useSearchParams: () => new URLSearchParams(mocks.search),
}));

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ username: "alice" }),
}));

vi.mock("@/contexts/ProjectContext", () => ({
  useProject: () => ({ projectId: "project-1", canEdit: true }),
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
  useGetExecution: () => ({
    data: undefined,
    isLoading: true,
    isError: false,
    error: null,
  }),
}));

const TABBABLE =
  'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

function isRendered(element: Element): boolean {
  for (let node: Element | null = element; node; node = node.parentElement) {
    if (getComputedStyle(node).display === "none") return false;
  }
  return true;
}

/**
 * Press Tab like a browser: the focused element gets the keydown, and unless a handler (the
 * dialog's focus trap) prevents it, focus moves to the next tabbable element in document order.
 */
function pressTab(shift = false): void {
  const active = document.activeElement ?? document.body;
  const proceed = fireEvent.keyDown(active, {
    key: "Tab",
    code: "Tab",
    shiftKey: shift,
  });
  if (!proceed) return;
  const order = Array.from(document.querySelectorAll<HTMLElement>(TABBABLE)).filter(
    (element) => element.tabIndex >= 0 && isRendered(element),
  );
  const index = order.indexOf(active as HTMLElement);
  const next = order[(index + (shift ? -1 : 1) + order.length) % order.length];
  act(() => next.focus());
}

/** Press Enter like a browser: a focused button is clicked unless the keydown is prevented. */
function pressEnter(): void {
  const active = document.activeElement as HTMLElement;
  if (fireEvent.keyDown(active, { key: "Enter", code: "Enter" }) && active.tagName === "BUTTON") {
    act(() => active.click());
  }
}

function pressEscape(): void {
  fireEvent.keyDown(document.activeElement ?? document.body, {
    key: "Escape",
    code: "Escape",
  });
}

function popover(): HTMLElement | null {
  return document.querySelector<HTMLElement>(".driver-popover");
}

async function waitForTitle(title: string): Promise<HTMLElement> {
  await waitFor(() =>
    expect(popover()?.querySelector(".driver-popover-title")?.textContent).toBe(title),
  );
  return popover() as HTMLElement;
}

function exitButton(): HTMLButtonElement {
  return screen.getByRole("button", { name: "Exit guide" });
}

function nextButton(): HTMLButtonElement {
  return popover()?.querySelector(".driver-popover-next-btn") as HTMLButtonElement;
}

interface TestDialogProps {
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
  children: React.ReactNode;
}

function TestDialog({ open = true, onOpenChange = () => {}, children }: TestDialogProps) {
  return (
    <>
      <button type="button">Page button</button>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent aria-describedby={undefined}>
          <DialogTitle>Guided dialog</DialogTitle>
          {children}
        </DialogContent>
      </Dialog>
    </>
  );
}

const CREATE_CHIP = (
  <>
    <input id="chip-id-input" aria-label="Chip ID" />
    <button type="button" data-coachmark="create-chip-submit">
      Create Chip
    </button>
  </>
);

const NEW_FLOW = (
  <>
    <div data-coachmark="flow-template" data-coachmark-ready="true">
      Template
    </div>
    <input data-coachmark="flow-name" aria-label="Flow name" />
    <button type="button" data-coachmark="flow-save">
      Save Flow
    </button>
  </>
);

describe("FirstCalibrationCoachmarks in a modal dialog", () => {
  beforeEach(() => {
    mocks.pathname = "/chip";
    mocks.search = "";
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

  it("puts an action step's Exit in the dialog's Tab loop without taking focus", async () => {
    storeJourney("project-1");
    render(
      <>
        <FirstCalibrationCoachmarks />
        <TestDialog>{CREATE_CHIP}</TestDialog>
      </>,
    );
    const wrapper = await waitForTitle("Name the chip");
    const dialog = screen.getByRole("dialog", { name: "Guided dialog" });
    const input = screen.getByLabelText("Chip ID");
    const submit = screen.getByRole("button", { name: "Create Chip" });

    // Inside the dialog's content, so not hidden from assistive technology with the page.
    expect(dialog.contains(wrapper)).toBe(true);
    expect(wrapper.closest('[aria-hidden="true"], [inert]')).toBeNull();
    // An action step has no Next; the dialog keeps the focus it gave the field.
    expect(nextButton().style.display).toBe("none");
    await act(async () => {});
    expect(document.activeElement).toBe(input);

    pressTab();
    expect(document.activeElement).toBe(submit);
    pressTab();
    expect(document.activeElement).toBe(exitButton());
    // Tab stays inside the modal: from the guide back to the dialog's first control.
    pressTab();
    expect(document.activeElement).toBe(input);
    pressTab(true);
    expect(document.activeElement).toBe(exitButton());
    pressTab(true);
    expect(document.activeElement).toBe(submit);

    // Showing the guide never ran the action it points at.
    expect(storedJourney("project-1")).toMatchObject({
      status: "active",
      chipId: null,
    });
  });

  it("pauses on Exit with Enter and returns focus to the control it pointed at", async () => {
    storeJourney("project-1");
    const onOpenChange = vi.fn();
    render(
      <>
        <FirstCalibrationCoachmarks />
        <TestDialog onOpenChange={onOpenChange}>{CREATE_CHIP}</TestDialog>
      </>,
    );
    await waitForTitle("Name the chip");
    pressTab(true);
    expect(document.activeElement).toBe(exitButton());

    pressEnter();
    await waitFor(() => expect(popover()).toBeNull());
    expect(storedJourney("project-1")).toMatchObject({ status: "paused" });
    expect(mocks.toastInfo).toHaveBeenCalledWith("Guide paused. Resume it from Home.");
    expect(onOpenChange).not.toHaveBeenCalled();
    expect(document.activeElement).toBe(screen.getByLabelText("Chip ID"));
    expect(document.querySelector(".driver-layer")).toBeNull();
  });

  it("pauses the guide on Escape from its buttons, and leaves Escape elsewhere to the dialog", async () => {
    storeJourney("project-1");
    const onOpenChange = vi.fn();
    render(
      <>
        <FirstCalibrationCoachmarks />
        <TestDialog onOpenChange={onOpenChange}>{CREATE_CHIP}</TestDialog>
      </>,
    );
    await waitForTitle("Name the chip");

    // Escape in the form is the dialog's: it asks to close, and the guide keeps going.
    pressEscape();
    expect(onOpenChange).toHaveBeenCalledWith(false);
    expect(storedJourney("project-1")).toMatchObject({ status: "active" });
    onOpenChange.mockClear();

    pressTab(true);
    expect(document.activeElement).toBe(exitButton());
    pressEscape();
    await waitFor(() => expect(popover()).toBeNull());
    expect(storedJourney("project-1")).toMatchObject({ status: "paused" });
    expect(onOpenChange).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog", { name: "Guided dialog" })).toBeTruthy();
    expect(document.activeElement).toBe(screen.getByLabelText("Chip ID"));
  });

  it("moves through explanations with Next by keyboard, then stops at the action", async () => {
    storeJourney("project-1", { chipId: "chip-a" });
    mocks.pathname = "/workflow/new";
    mocks.search = "journey=first-calibration";
    render(
      <>
        <FirstCalibrationCoachmarks />
        <TestDialog>{NEW_FLOW}</TestDialog>
      </>,
    );
    await waitForTitle("Review the calibration");
    const flowName = screen.getByLabelText("Flow name");
    const save = screen.getByRole("button", { name: "Save Flow" });
    await act(async () => {});
    expect(document.activeElement).toBe(flowName);

    pressTab();
    expect(document.activeElement).toBe(save);
    pressTab();
    expect(document.activeElement).toBe(exitButton());
    pressTab();
    expect(document.activeElement).toBe(nextButton());
    pressTab();
    expect(document.activeElement).toBe(flowName);
    pressTab(true);
    expect(document.activeElement).toBe(nextButton());

    // Next keeps focus in the guide, on the next popover's Next.
    pressEnter();
    await waitForTitle("Name the flow");
    await waitFor(() => expect(document.activeElement).toBe(nextButton()));
    pressEnter();
    // The action step has only Exit; focus lands there instead of dropping to the page.
    await waitForTitle("Save the flow");
    await waitFor(() => expect(document.activeElement).toBe(exitButton()));
    expect(nextButton().style.display).toBe("none");
    expect(storedJourney("project-1")).toMatchObject({
      status: "active",
      flowName: null,
    });

    pressTab();
    expect(document.activeElement).toBe(flowName);
  });

  it("hosts the popover in the top layer where the Popover API exists", async () => {
    const showPopover = vi.fn();
    Object.defineProperty(HTMLElement.prototype, "showPopover", {
      configurable: true,
      value: showPopover,
    });
    try {
      storeJourney("project-1");
      render(
        <>
          <FirstCalibrationCoachmarks />
          <TestDialog>{CREATE_CHIP}</TestDialog>
        </>,
      );
      const wrapper = await waitForTitle("Name the chip");
      const layer = wrapper.parentElement as HTMLElement;
      expect(layer.classList.contains("driver-layer")).toBe(true);
      expect(layer.getAttribute("popover")).toBe("manual");
      expect(showPopover).toHaveBeenCalled();
      expect(layer.parentElement).toBe(screen.getByRole("dialog", { name: "Guided dialog" }));
    } finally {
      delete (HTMLElement.prototype as { showPopover?: unknown }).showPopover;
    }
  });

  it("leaves no nodes or listeners behind when the dialog closes or the guide unmounts", async () => {
    const added: Array<[EventTarget, string, unknown]> = [];
    const removed: Array<[EventTarget, string, unknown]> = [];
    for (const target of [window, document] as EventTarget[]) {
      const add = target.addEventListener.bind(target);
      const remove = target.removeEventListener.bind(target);
      vi.spyOn(target, "addEventListener").mockImplementation((type, listener, options) => {
        added.push([target, type, listener]);
        add(type, listener, options);
      });
      vi.spyOn(target, "removeEventListener").mockImplementation((type, listener, options) => {
        removed.push([target, type, listener]);
        remove(type, listener, options);
      });
    }

    storeJourney("project-1");
    const page = (open: boolean) => (
      <>
        <FirstCalibrationCoachmarks />
        <TestDialog open={open}>{CREATE_CHIP}</TestDialog>
      </>
    );
    const { rerender, unmount } = render(page(true));
    await waitForTitle("Name the chip");
    pressTab(true);
    expect(document.activeElement).toBe(exitButton());

    rerender(page(false));
    // The dialog takes the hosted popover with it; the guide clears the rest on its next frame.
    await waitFor(() => {
      expect(popover()).toBeNull();
      expect(document.querySelector(".driver-layer, .driver-overlay")).toBeNull();
    });
    expect(document.querySelector(".qdash-coachmark-target")).toBeNull();
    expect(document.body.classList.contains("driver-active")).toBe(false);
    // Closing the dialog is not exiting the guide.
    expect(storedJourney("project-1")).toMatchObject({ status: "active" });

    rerender(page(true));
    await waitForTitle("Name the chip");
    unmount();
    expect(popover()).toBeNull();
    expect(document.querySelector(".driver-layer, .driver-overlay")).toBeNull();

    const left = added.filter(
      ([target, type, listener]) =>
        // React keeps one document-level listener for the root for its whole life.
        type !== "selectionchange" &&
        !removed.some(([t, ty, l]) => t === target && ty === type && l === listener),
    );
    expect(
      left.map(([target, type]) => `${target === window ? "window" : "document"}:${type}`),
    ).toEqual([]);
  });
});

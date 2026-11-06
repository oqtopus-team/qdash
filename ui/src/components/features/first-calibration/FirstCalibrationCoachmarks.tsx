"use client";

import { usePathname, useSearchParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { driver, type PopoverDOM } from "driver.js";
import "driver.js/dist/driver.css";

import { useToast } from "@/components/ui/Toast";

import { findCurrentCoachmark, type CurrentCoachmark } from "./coachmarkDom";
import { resolveCoachmarkPlan, type CoachmarkStep } from "./coachmarkPlan";
import { useFirstCalibrationJourney } from "./useFirstCalibrationJourney";
import { useFirstCalibrationProgress, useJourneyScope } from "./useFirstCalibrationProgress";

const POPOVER_CLASS = "qdash-coachmark";
/** Ring on the control a step asks the user to use. */
const TARGET_CLASS = "qdash-coachmark-target";
/** Attributes whose change can show, hide or ready a target. */
const WATCHED_ATTRIBUTES = [
  "class",
  "hidden",
  "inert",
  "aria-hidden",
  "disabled",
  "open",
  "data-coachmark-ready",
];

function escapeHtml(value: string): string {
  return value
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function sameCoachmark(a: CurrentCoachmark | null, b: CurrentCoachmark | null): boolean {
  if (a === null || b === null) return a === b;
  return (
    a.element === b.element &&
    a.step.id === b.step.id &&
    a.step.title === b.step.title &&
    a.step.description === b.step.description
  );
}

/**
 * The step on screen now, re-read whenever the page changes: a target mounting or unmounting
 * (dialogs, loaded data, route changes), an input being filled or left.
 */
function useCurrentCoachmark(
  steps: readonly CoachmarkStep[] | null,
  isRead: (stepId: string) => boolean,
): CurrentCoachmark | null {
  const [current, setCurrent] = useState<CurrentCoachmark | null>(null);

  useEffect(() => {
    if (!steps) {
      setCurrent(null);
      return;
    }
    let frame = 0;
    const evaluate = () => {
      frame = 0;
      const next = findCurrentCoachmark(steps, isRead);
      setCurrent((previous) => (sameCoachmark(previous, next) ? previous : next));
    };
    const schedule = () => {
      if (frame === 0) frame = window.requestAnimationFrame(evaluate);
    };
    evaluate();
    const observer = new MutationObserver(schedule);
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: WATCHED_ATTRIBUTES,
    });
    // Inputs, focus moves, and the end of slide-overs that uncover a target.
    const documentEvents = ["input", "focusin", "focusout", "transitionend", "animationend"];
    for (const type of documentEvents) document.addEventListener(type, schedule, true);
    window.addEventListener("resize", schedule);
    return () => {
      if (frame !== 0) window.cancelAnimationFrame(frame);
      observer.disconnect();
      for (const type of documentEvents) document.removeEventListener(type, schedule, true);
      window.removeEventListener("resize", schedule);
    };
  }, [steps, isRead]);

  return steps ? current : null;
}

function prefersReducedMotion(): boolean {
  return window.matchMedia?.("(prefers-reduced-motion: reduce)").matches ?? false;
}

interface CoachmarkHandlers {
  onNext: (stepId: string) => void;
  onExit: () => void;
}

/** An open Radix dialog: the focus trap, outside-click and `aria-hidden` scope of a modal. */
const OPEN_DIALOG_SELECTOR =
  '[role="dialog"][data-state="open"], [role="alertdialog"][data-state="open"]';
/** Class driver.js gives its own popover layer; it removes the layer with its last popover. */
const LAYER_CLASS = "driver-layer";
const FOCUSABLE_SELECTOR =
  'a[href], button:not([disabled]), input:not([disabled]):not([type="hidden"]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])';

/**
 * Move the popover into the open dialog that holds the target. A modal dialog traps focus and Tab
 * inside its content, hides the rest of the page from assistive technology and treats a click
 * anywhere else as outside, so a popover on <body> could be seen but never reached by keyboard.
 *
 * Inside the dialog's content the guide's buttons join its Tab loop. The layer is a manual
 * popover, as driver.js does for a native <dialog>, so it renders in the top layer at viewport
 * coordinates and the dialog's transform and scrolling cannot clip or shift it.
 */
function hostPopoverInDialog(popover: PopoverDOM, target: HTMLElement): HTMLElement | null {
  // driver.js already hosts popovers of a native <dialog> itself.
  if (popover.wrapper.parentElement !== document.body) return null;
  const dialog = target.closest<HTMLElement>(OPEN_DIALOG_SELECTOR);
  if (!dialog) return null;
  const layer = document.createElement("div");
  layer.className = LAYER_CLASS;
  dialog.appendChild(layer);
  if (typeof layer.showPopover === "function") {
    layer.setAttribute("popover", "manual");
    layer.showPopover();
  }
  layer.appendChild(popover.wrapper);
  return dialog;
}

function isFocusable(element: HTMLElement): boolean {
  return (
    element.isConnected &&
    element.matches(FOCUSABLE_SELECTOR) &&
    !element.closest('[inert], [hidden], [aria-hidden="true"]')
  );
}

/** Focus the first control of the dialog that is not the guide's, or the dialog itself. */
function focusFirstOutside(dialog: HTMLElement, guide: HTMLElement): void {
  const first = Array.from(dialog.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR)).find(
    (candidate) => !guide.contains(candidate) && candidate.tabIndex >= 0 && isFocusable(candidate),
  );
  (first ?? dialog).focus({ preventScroll: true });
}

interface FocusSnapshot {
  element: HTMLElement;
  selection: {
    start: number;
    end: number;
    direction: "forward" | "backward" | "none";
  } | null;
}

/** Where focus is now, with the caret of a text field, so it can be put back exactly. */
function snapshotFocus(): FocusSnapshot | null {
  const element = document.activeElement;
  if (!(element instanceof HTMLElement) || element === document.body) return null;
  let selection: FocusSnapshot["selection"] = null;
  if (element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement) {
    try {
      if (element.selectionStart !== null && element.selectionEnd !== null) {
        selection = {
          start: element.selectionStart,
          end: element.selectionEnd,
          direction: element.selectionDirection ?? "none",
        };
      }
    } catch {
      // Input types without a caret, such as number on older engines.
    }
  }
  return { element, selection };
}

function restoreFocus(snapshot: FocusSnapshot): void {
  const { element, selection } = snapshot;
  if (!element.isConnected) return;
  element.focus({ preventScroll: true });
  if (
    selection &&
    (element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement)
  ) {
    try {
      element.setSelectionRange(selection.start, selection.end, selection.direction);
    } catch {
      // The field no longer has a caret.
    }
  }
}

/**
 * Spotlight one target with driver.js. The highlight is layered over the page, never in its way:
 * the overlay lets every click through, sits below dialogs, and the page keeps its own focus and
 * Tab order (driver.js would otherwise move focus into the popover and trap Tab there). Inside a
 * modal dialog the popover joins the dialog, so its buttons stay in the dialog's Tab loop.
 */
function useCoachmarkHighlight(
  current: CurrentCoachmark | null,
  progressText: string,
  handlers: CoachmarkHandlers,
): void {
  const latest = useRef(handlers);
  useEffect(() => {
    latest.current = handlers;
  });
  // Set when a popover goes away while focus is on its buttons (Next, Exit, Escape, a step
  // change), so focus follows into the next popover instead of dropping to the page.
  const focusNextPopover = useRef(false);
  const popoverRef = useRef<PopoverDOM | null>(null);
  const step = current?.element ? current.step : null;
  const stepRef = useRef(step);
  useEffect(() => {
    stepRef.current = step;
  });
  const element = current?.element ?? null;
  const stepId = step?.id ?? null;

  useEffect(() => {
    const shown = stepRef.current;
    if (!element || !shown) return;
    const target = element;
    const reduceMotion = prefersReducedMotion();
    let rendered: PopoverDOM | null = null;
    let dialog: HTMLElement | null = null;
    let tornDown = false;

    const onPopoverRender = (popover: PopoverDOM) => {
      popoverRef.current = popover;
      rendered = popover;
      const before = snapshotFocus();
      dialog = hostPopoverInDialog(popover, target);
      popover.closeButton.title = "Exit guide";
      // Clicking the popover text must not count as a click outside an open dialog.
      popover.wrapper.addEventListener("pointerdown", (event) => event.stopPropagation());
      // Taken now, so a pending fallback from the previous popover sees it handled.
      const followFocus = focusNextPopover.current;
      focusNextPopover.current = false;
      // driver.js focuses the popover after this hook; put focus back where the user had it.
      queueMicrotask(() => {
        if (followFocus) {
          const next = popover.nextButton;
          (next.style.display !== "none" ? next : popover.closeButton).focus();
          return;
        }
        if (before && !popover.wrapper.contains(before.element) && before.element.isConnected) {
          restoreFocus(before);
        } else if (
          document.activeElement instanceof HTMLElement &&
          popover.wrapper.contains(document.activeElement)
        ) {
          // Nothing had focus: the dialog may be opening, and with focus already inside it, it
          // skips its own first focus. Give it the focus it would have, outside the guide.
          if (dialog) focusFirstOutside(dialog, popover.wrapper);
          else document.activeElement.blur();
        }
      });
    };

    const instance = driver({
      animate: !reduceMotion,
      smoothScroll: !reduceMotion,
      allowClose: true,
      allowScroll: true,
      allowKeyboardControl: false,
      overlayClickBehavior: "none",
      overlayOpacity: shown.dim ? 0.4 : 0,
      stagePadding: shown.kind === "wait" ? 0 : 6,
      stageRadius: 10,
      popoverClass: POPOVER_CLASS,
      onPopoverRender,
    });

    // The page scrolls inside <main>, not the window, so follow every scroll container, and a
    // dialog that slides into place after the popover first rendered.
    const refresh = () => instance.refresh();
    const settleEvents = ["transitionend", "animationend"] as const;
    const resizeObserver =
      typeof ResizeObserver === "undefined" ? null : new ResizeObserver(refresh);
    // driver.js traps Tab on window; stop Tab there so the page keeps its own Tab order.
    const keepTabOrder = (event: KeyboardEvent) => {
      if (event.key === "Tab") event.stopPropagation();
    };
    // Escape on the guide's own buttons pauses the guide and leaves an open dialog open. It runs
    // on window in the capture phase, ahead of the dialog's own Escape handler on document.
    // Escape anywhere else stays the page's: it closes the dialog as usual.
    const pauseOnEscape = (event: KeyboardEvent) => {
      if (event.key !== "Escape" || !rendered) return;
      if (!(event.target instanceof Node) || !rendered.wrapper.contains(event.target)) return;
      event.preventDefault();
      event.stopPropagation();
      teardown();
      latest.current.onExit();
    };

    function teardown() {
      if (tornDown) return;
      tornDown = true;
      const focusWasInGuide =
        rendered !== null &&
        rendered.wrapper.isConnected &&
        document.activeElement instanceof Node &&
        rendered.wrapper.contains(document.activeElement);
      document.removeEventListener("scroll", refresh, { capture: true });
      for (const type of settleEvents) document.removeEventListener(type, refresh, true);
      document.removeEventListener("keydown", keepTabOrder);
      window.removeEventListener("keydown", pauseOnEscape, { capture: true });
      resizeObserver?.disconnect();
      target.classList.remove(TARGET_CLASS);
      popoverRef.current = null;
      const layer = rendered?.wrapper.parentElement;
      instance.destroy();
      // driver.js drops an emptied layer of its own; never leave one behind in the dialog.
      if (layer?.classList.contains(LAYER_CLASS) && layer.childElementCount === 0) layer.remove();
      if (!focusWasInGuide) return;
      // Focus was on the guide's buttons. A popover shown in the same update takes it;
      // otherwise it goes back to the control the guide pointed at, or to the dialog.
      focusNextPopover.current = true;
      const host = dialog;
      queueMicrotask(() => {
        if (!focusNextPopover.current) return;
        focusNextPopover.current = false;
        const active = document.activeElement;
        if (active instanceof HTMLElement && active !== document.body && active !== host) return;
        if (isFocusable(target)) target.focus({ preventScroll: true });
        else if (host?.isConnected) host.focus({ preventScroll: true });
      });
    }

    instance.highlight({
      element: target,
      popover: {
        title: escapeHtml(shown.title),
        description: escapeHtml(shown.description),
        side: shown.side,
        align: shown.align,
        showButtons: shown.kind === "info" ? ["next", "close"] : ["close"],
        showProgress: true,
        progressText: escapeHtml(progressText),
        nextBtnText: escapeHtml(shown.nextLabel ?? "Next"),
        closeBtnLabel: "Exit guide",
        onNextClick: () => {
          latest.current.onNext(shown.id);
        },
        onCloseClick: () => {
          teardown();
          latest.current.onExit();
        },
      },
    });
    // driver.js disables pointer events on the whole page while it is active; the guide only
    // points, so the page stays usable.
    document.body.classList.remove("driver-active");
    if (shown.kind !== "wait") target.classList.add(TARGET_CLASS);

    document.addEventListener("scroll", refresh, {
      capture: true,
      passive: true,
    });
    for (const type of settleEvents) document.addEventListener(type, refresh, true);
    resizeObserver?.observe(target);
    // A centered dialog moves its controls when its content grows or shrinks.
    const hostDialog = dialog as HTMLElement | null;
    if (hostDialog) resizeObserver?.observe(hostDialog);
    document.addEventListener("keydown", keepTabOrder);
    window.addEventListener("keydown", pauseOnEscape, { capture: true });

    return teardown;
  }, [element, stepId, progressText]);

  // A wait step's counts change while it is shown; update the text in place instead of
  // highlighting again.
  const title = step?.title;
  const description = step?.description;
  useEffect(() => {
    const popover = popoverRef.current;
    if (!popover || title === undefined || description === undefined) return;
    if (popover.title.textContent !== title) popover.title.textContent = title;
    if (popover.description.textContent !== description) {
      popover.description.textContent = description;
    }
  }, [title, description]);
}

/**
 * Step-by-step coachmarks of the first calibration journey, layered over the pages the journey
 * passes through. They point at the real control to use next: the chip ID field and Create Chip,
 * the template, flow name and Save Flow, Execute and its confirmation, the result to open, its
 * graph and values, and the chip overview.
 *
 * Where the journey is comes from its stored ids and the server records they name, never from
 * this component: action steps move on only when the real action changes that progress, and only
 * explanation steps have Next. Closing a coachmark pauses the journey; Home resumes it at the
 * step the records point to. Viewers and users without an active journey get nothing.
 */
export function FirstCalibrationCoachmarks() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const journeyParam = searchParams.get("journey");
  const toast = useToast();
  const journey = useFirstCalibrationJourney();
  const scope = useJourneyScope();
  const active = journey.state?.status === "active" ? journey.state : null;
  const { progress, setup } = useFirstCalibrationProgress(active);

  const plan = useMemo(
    () =>
      active && progress
        ? resolveCoachmarkPlan({
            state: active,
            progress,
            setup,
            pathname,
            journeyParam,
          })
        : null,
    [active, progress, setup, pathname, journeyParam],
  );

  // Explanations read with Next, remembered for this user, project and journey only.
  const readKey =
    active && scope ? JSON.stringify([scope.username, scope.projectId, active.startedAt]) : null;
  const [read, setRead] = useState<{
    key: string | null;
    ids: ReadonlySet<string>;
  }>({
    key: null,
    ids: new Set(),
  });
  const isRead = useCallback(
    (stepId: string) => read.key === readKey && read.ids.has(stepId),
    [read, readKey],
  );
  const markRead = useCallback(
    (stepId: string) =>
      setRead((previous) => ({
        key: readKey,
        ids: new Set(previous.key === readKey ? [...previous.ids, stepId] : [stepId]),
      })),
    [readKey],
  );

  const current = useCurrentCoachmark(plan?.steps ?? null, isRead);

  const record = journey.record;

  // The result counts as inspected once its explanation is over: at least one explanation was
  // read with Next and the guide has moved past them all (to the next step, or nothing). Until
  // then the progress stays on the result step the guide is explaining. The page is read again
  // here, since `current` may still describe the plan shown before this one (a resume, say).
  useEffect(() => {
    const completion = plan?.completion;
    if (!plan || !completion || !completion.stepIds.some(isRead)) return;
    const now = findCurrentCoachmark(plan.steps, isRead);
    if (now && completion.stepIds.includes(now.step.id)) return;
    record(completion.event);
  }, [plan, isRead, current, record]);

  const exit = useCallback(() => {
    record({ type: "pause" });
    toast.info("Guide paused. Resume it from Home.");
  }, [record, toast]);

  useCoachmarkHighlight(current, plan?.progressText ?? "", {
    onNext: markRead,
    onExit: exit,
  });

  const shown = current?.element ? current.step : null;
  return (
    <div className="sr-only" role="status" aria-live="polite" aria-atomic="true">
      {shown ? `First calibration guide: ${shown.title}. ${shown.description}` : ""}
    </div>
  );
}

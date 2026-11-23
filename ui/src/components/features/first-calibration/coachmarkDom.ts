import type { CoachmarkStep } from "./coachmarkPlan";

/**
 * Whether another layer, such as a slide-over panel, covers the middle of the element. A point
 * outside the viewport counts as uncovered, since the highlight scrolls the element into view.
 */
function isCovered(element: Element, rect: DOMRect): boolean {
  const doc = element.ownerDocument;
  if (typeof doc.elementFromPoint !== "function") return false;
  const x = rect.left + rect.width / 2;
  const y = rect.top + rect.height / 2;
  const view = doc.defaultView;
  if (!view || x < 0 || y < 0 || x > view.innerWidth || y > view.innerHeight) return false;
  const hit = doc.elementFromPoint(x, y);
  if (!hit || element.contains(hit) || hit.contains(element)) return false;
  // The guide's own popover never hides a target.
  return !hit.closest(".driver-popover");
}

/**
 * Whether an element is on screen and usable: rendered with a size, not inert, hidden or covered
 * by another layer.
 */
function isCoachmarkTargetVisible(element: Element): boolean {
  if (!element.isConnected) return false;
  if (element.closest('[inert], [hidden], [aria-hidden="true"]')) return false;
  const rect = Array.from(element.getClientRects()).find(
    (item) => item.width > 0 && item.height > 0,
  );
  return rect !== undefined && !isCovered(element, element.getBoundingClientRect());
}

/** The first visible element any of the selectors names, or null. */
function findCoachmarkTarget(
  targets: readonly string[],
  root: ParentNode = document,
): HTMLElement | null {
  for (const selector of targets) {
    let candidates: NodeListOf<HTMLElement>;
    try {
      candidates = root.querySelectorAll<HTMLElement>(selector);
    } catch {
      continue;
    }
    for (const candidate of Array.from(candidates)) {
      if (isCoachmarkTargetVisible(candidate)) return candidate;
    }
  }
  return null;
}

function isFilledAndLeft(element: HTMLElement): boolean {
  const value =
    element instanceof HTMLInputElement || element instanceof HTMLTextAreaElement
      ? element.value
      : "";
  // While the user is still typing, the coachmark stays on the field.
  return value.trim() !== "" && element.ownerDocument.activeElement !== element;
}

export interface CurrentCoachmark {
  step: CoachmarkStep;
  /** The target on screen, or null while the step waits for it to appear. */
  element: HTMLElement | null;
}

/**
 * The step the guide shows now: the first step that is neither read (info), filled (an input the
 * user has left) nor optional with no target on screen. A step whose target is not on screen yet
 * is returned with a null element, so the guide waits for the page instead of skipping ahead.
 */
export function findCurrentCoachmark(
  steps: readonly CoachmarkStep[],
  isRead: (stepId: string) => boolean,
  root: ParentNode = document,
): CurrentCoachmark | null {
  for (const step of steps) {
    if (step.kind === "info" && isRead(step.id)) continue;
    const element = findCoachmarkTarget(step.targets, root);
    if (!element) {
      if (step.optional) continue;
      return { step, element: null };
    }
    if (step.doneWhenFilled && isFilledAndLeft(element)) continue;
    return { step, element };
  }
  return null;
}

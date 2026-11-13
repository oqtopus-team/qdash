import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { findCurrentCoachmark } from "@/components/features/first-calibration/coachmarkDom";
import type { CoachmarkStep } from "@/components/features/first-calibration/coachmarkPlan";

function step(overrides: Partial<CoachmarkStep> & Pick<CoachmarkStep, "id">): CoachmarkStep {
  return {
    kind: "action",
    title: overrides.id,
    description: "",
    targets: [`#${overrides.id}`],
    dim: true,
    ...overrides,
  };
}

const notRead = () => false;

describe("findCurrentCoachmark", () => {
  beforeEach(() => {
    // jsdom has no layout; give every element a size so it counts as on screen.
    vi.spyOn(Element.prototype, "getClientRects").mockImplementation(
      () => [{ width: 10, height: 10 }] as unknown as DOMRectList,
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
    document.body.innerHTML = "";
  });

  it("waits for a required target instead of skipping ahead", () => {
    document.body.innerHTML = '<button id="later"></button>';
    const current = findCurrentCoachmark([step({ id: "first" }), step({ id: "later" })], notRead);
    expect(current?.step.id).toBe("first");
    expect(current?.element).toBeNull();
  });

  it("skips an optional step whose target is not on screen", () => {
    document.body.innerHTML = '<button id="open"></button>';
    const current = findCurrentCoachmark(
      [step({ id: "inside", optional: true }), step({ id: "open" })],
      notRead,
    );
    expect(current?.step.id).toBe("open");
    expect(current?.element).toBe(document.getElementById("open"));
  });

  it("ignores targets that are inert or hidden from assistive technology", () => {
    document.body.innerHTML =
      '<div inert><button id="a"></button></div><div aria-hidden="true"><button id="b"></button></div>';
    expect(
      findCurrentCoachmark(
        [step({ id: "a", optional: true }), step({ id: "b", optional: true })],
        notRead,
      ),
    ).toBeNull();
  });

  it("keeps a field's step while the user types, and moves on once they leave it", () => {
    document.body.innerHTML = '<input id="name" /><button id="submit"></button>';
    const input = document.getElementById("name") as HTMLInputElement;
    const steps = [
      step({ id: "name", optional: true, doneWhenFilled: true }),
      step({ id: "submit" }),
    ];

    expect(findCurrentCoachmark(steps, notRead)?.step.id).toBe("name");
    input.focus();
    input.value = "chip-a";
    expect(findCurrentCoachmark(steps, notRead)?.step.id).toBe("name");
    input.blur();
    expect(findCurrentCoachmark(steps, notRead)?.step.id).toBe("submit");
  });

  it("moves past an explanation only once it was read", () => {
    document.body.innerHTML = '<div id="review"></div><button id="save"></button>';
    const steps = [step({ id: "review", kind: "info" }), step({ id: "save" })];
    expect(findCurrentCoachmark(steps, notRead)?.step.id).toBe("review");
    expect(findCurrentCoachmark(steps, (id) => id === "review")?.step.id).toBe("save");
  });

  it("does not let an action step be read past", () => {
    document.body.innerHTML = '<button id="save"></button>';
    expect(findCurrentCoachmark([step({ id: "save" })], () => true)?.step.id).toBe("save");
  });
});

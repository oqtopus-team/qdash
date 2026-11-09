import { describe, expect, it } from "vitest";

import {
  parseUiBlock,
  safeInternalHref,
  uiSpecToText,
  validateUiSpec,
  type UiSpec,
} from "../copilotUiSpec";

const spec: UiSpec = {
  root: "card",
  elements: {
    card: { type: "Card", props: { title: "Q03 coherence" }, children: ["t1", "alert", "link"] },
    t1: { type: "Metric", props: { label: "T1", value: 42.1, unit: "us" }, children: [] },
    alert: {
      type: "Alert",
      props: { tone: "warning", message: "T2 echo dropped 30%" },
      children: [],
    },
    link: {
      type: "Link",
      props: { label: "Open qubit", href: "/chip/64Qv3/qubit/3" },
      children: [],
    },
  },
};

describe("copilotUiSpec", () => {
  it("accepts a catalog spec and fills in missing children", () => {
    const { t1, ...rest } = spec.elements;
    const { children: _children, ...leaf } = t1;
    const result = validateUiSpec({ ...spec, elements: { ...rest, t1: leaf } });
    expect(result.ok).toBe(true);
    if (result.ok) expect(result.spec.elements.t1.children).toEqual([]);
  });

  it("rejects specs a model or a tampered message could produce", () => {
    const cases: unknown[] = [
      null,
      [],
      "spec",
      { root: "a", elements: { a: { type: "Script", props: {} } } },
      { root: "a", elements: { a: { type: "Text", props: { text: "x", html: "<b>" } } } },
      { root: "a", elements: { a: { type: "Text", props: { text: { $state: "/x" } } } } },
      { root: "a", elements: { a: { type: "Text", props: { text: "x" }, on: { press: {} } } } },
      { root: "a", elements: { a: { type: "Stack", props: {}, children: ["a"] } } },
      {
        root: "a",
        elements: { a: { type: "Link", props: { label: "x", href: "javascript:alert(1)" } } },
      },
      { ...spec, state: {} },
    ];
    for (const value of cases) expect(validateUiSpec(value).ok).toBe(false);
  });

  it("only allows internal QDash page links", () => {
    expect(safeInternalHref("/task-results/abc?x=1#y")).toBe("/task-results/abc?x=1#y");
    expect(safeInternalHref("/chip/../admin")).toBeNull();
    expect(safeInternalHref("https://example.com/chip")).toBeNull();
    expect(safeInternalHref("//example.com/chip")).toBeNull();
    expect(safeInternalHref("/\\example.com")).toBeNull();
    expect(safeInternalHref("data:text/html,x")).toBeNull();
  });

  it("renders the spec as plain text for copying and fallbacks", () => {
    expect(uiSpecToText(spec)).toBe(
      [
        "### Q03 coherence",
        "- T1: 42.1 us",
        "> **WARNING** T2 echo dropped 30%",
        "Open qubit: /chip/64Qv3/qubit/3",
      ].join("\n\n"),
    );
  });

  it("keeps only the fallback for unknown versions and invalid specs", () => {
    expect(parseUiBlock({ version: 1, spec, fallback: "f" }).status).toBe("ok");
    expect(parseUiBlock({ version: 2, spec, fallback: "f" })).toEqual({
      status: "fallback",
      fallback: "f",
    });
    expect(parseUiBlock({ version: 1, spec: { root: "x" }, fallback: "f" })).toEqual({
      status: "fallback",
      fallback: "f",
    });
    expect(parseUiBlock("nope")).toEqual({ status: "fallback", fallback: "" });
  });
});

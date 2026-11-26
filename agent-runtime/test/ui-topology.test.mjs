import assert from "node:assert/strict";
import { test } from "node:test";

import { validateToolArguments } from "@earendil-works/pi-ai/utils/validation";

import { UI_SPEC_LIMITS, uiBlockFromDetails, uiTool, validateUiSpec } from "../src/ui-tool.ts";
import { normalizeUiTopology } from "../src/ui-topology.ts";

async function callAsHarness(args) {
  const prepared = uiTool.prepareArguments(args);
  const validated = validateToolArguments(uiTool, {
    type: "toolCall",
    id: "c1",
    name: uiTool.name,
    arguments: prepared,
  });
  return uiTool.execute(validated);
}

const table = {
  id: "t",
  caption: "Qubits",
  columns: [
    { key: "qid", label: "Qubit" },
    { key: "t1", label: "T1 (us)", align: "right" },
  ],
  rows: [["Q00", 41.2], ["Q01", 38.9]],
};

/**
 * The reported call: the root stack lists the table that its card already
 * holds, and two alerts and a text are in no children list.
 */
const reported = {
  root: "s",
  stacks: [{ id: "s", children: ["m", "f", "t", "l"] }],
  cards: [{ id: "f", title: "Coherence", children: ["t"] }],
  metrics: [{ id: "m", label: "Median T1", value: 40.1, unit: "us" }],
  tables: [table],
  alerts: [
    { id: "a1", tone: "warning", title: "Drift", message: "Q01 T1 dropped 8%" },
    { id: "a2", tone: "info", message: "Data from the latest execution" },
  ],
  texts: [{ id: "tx1", text: "Values come from get_qubit_metrics.", variant: "muted" }],
  charts: [],
  links: [{ id: "l", label: "Chip", href: "/chip/64Qv3" }],
};

function countIn(spec, id) {
  return Object.values(spec.elements).filter((element) => element.children.includes(id)).length;
}

test("the reported call renders with the table once and the alerts and text kept", async () => {
  const snapshot = JSON.stringify(reported);
  const result = await callAsHarness(reported);
  assert.equal(JSON.stringify(reported), snapshot, "the call's arguments are not modified");

  const { spec, fallback } = result.details.ui;
  assert.equal(spec.root, "s");
  assert.deepEqual(spec.elements.s.children, ["m", "f", "l", "a1", "a2", "tx1"]);
  assert.deepEqual(spec.elements.f.children, ["t"]);
  for (const id of ["m", "f", "t", "l", "a1", "a2", "tx1"]) assert.equal(countIn(spec, id), 1, id);
  assert.equal(fallback.match(/\| Qubit \| T1 \(us\) \|/g).length, 1, "the table appears once");
  assert.match(fallback, /WARNING\*\* Drift: Q01 T1 dropped 8%/);
  assert.match(fallback, /Data from the latest execution/);
  assert.match(fallback, /Values come from get_qubit_metrics\./);

  // The stored block passes the chat's strict validation unchanged.
  assert.equal(validateUiSpec(spec).ok, true);
  assert.deepEqual(uiBlockFromDetails(result.details), result.details.ui);

  const note = result.output[0].text;
  assert.match(note, /UI rendered in the chat \(8 elements\)/);
  assert.match(note, /removed "t" from "s"\.children; it is already inside "f"/);
  assert.match(note, /added the unplaced "a1", "a2", "tx1" to the end of the root stack "s"/);
  assert.match(note, /Next time list each element in the children of exactly one container/);
});

test("the earlier spec form gets the same repairs", async () => {
  const spec = {
    root: "s",
    elements: {
      s: { type: "Stack", props: {}, children: ["f", "t", "t"] },
      f: { type: "Card", props: {}, children: ["t"] },
      t: { type: "Text", props: { text: "x" }, children: [] },
      a: { type: "Alert", props: { tone: "info", message: "y" }, children: [] },
    },
  };
  const snapshot = JSON.stringify(spec);
  const { details } = await callAsHarness({ spec: JSON.stringify(spec) });
  assert.deepEqual(details.ui.spec.elements.s.children, ["f", "a"]);
  assert.deepEqual(details.ui.spec.elements.f.children, ["t"]);
  await callAsHarness({ spec });
  assert.equal(JSON.stringify(spec), snapshot);
});

test("a repeated child is listed once", async () => {
  const { details, output } = await callAsHarness({
    root: "s",
    stacks: [{ id: "s", children: ["a", "b", "a"] }],
    texts: [{ id: "a", text: "A" }, { id: "b", text: "B" }],
  });
  assert.deepEqual(details.ui.spec.elements.s.children, ["a", "b"]);
  assert.match(output[0].text, /removed the repeated "a" from "s"\.children/);
});

test("a redundant reference two levels up keeps the nearest parent", () => {
  const { spec, repairs } = normalizeUiTopology({
    root: "s",
    elements: {
      s: { type: "Stack", props: {}, children: ["c", "t"] },
      c: { type: "Card", props: {}, children: ["s2"] },
      s2: { type: "Stack", props: {}, children: ["t"] },
      t: { type: "Text", props: { text: "x" }, children: [] },
    },
  });
  assert.deepEqual(spec.elements.s.children, ["c"]);
  assert.deepEqual(spec.elements.s2.children, ["t"]);
  assert.equal(repairs.length, 1);
  assert.equal(validateUiSpec(spec).ok, true);
});

test("orphans are wrapped with the root when the root is not a vertical stack", async () => {
  const horizontal = await callAsHarness({
    root: "s",
    stacks: [{ id: "s", direction: "horizontal", children: ["m"] }],
    metrics: [{ id: "m", label: "T1", value: 1 }],
    alerts: [{ id: "a", tone: "info", message: "x" }],
  });
  const spec = horizontal.details.ui.spec;
  assert.equal(spec.root, "ui-root");
  assert.deepEqual(spec.elements["ui-root"], {
    type: "Stack",
    props: { direction: "vertical" },
    children: ["s", "a"],
  });
  assert.deepEqual(spec.elements.s.children, ["m"]);
  assert.match(horizontal.output[0].text, /wrapped the root "s" and the unplaced "a" in a new vertical stack "ui-root"/);

  // A leaf root, and an id already taken by the model.
  const leaf = await callAsHarness({
    root: "m",
    metrics: [{ id: "m", label: "T1", value: 1 }],
    texts: [{ id: "ui-root", text: "taken" }],
  });
  assert.equal(leaf.details.ui.spec.root, "ui-root-2");
  assert.deepEqual(leaf.details.ui.spec.elements["ui-root-2"].children, ["m", "ui-root"]);

  // A card root is wrapped rather than given the orphans.
  const card = await callAsHarness({
    root: "c",
    cards: [{ id: "c", title: "Q03", children: [] }],
    texts: [{ id: "x", text: "outside" }],
  });
  assert.deepEqual(card.details.ui.spec.elements.c.children, []);
  assert.deepEqual(card.details.ui.spec.elements[card.details.ui.spec.root].children, ["c", "x"]);
});

test("an orphan container keeps its subtree", async () => {
  const { details } = await callAsHarness({
    root: "s",
    stacks: [{ id: "s", children: ["m"] }],
    cards: [{ id: "c", title: "Extra", children: ["t"] }],
    metrics: [{ id: "m", label: "T1", value: 1 }],
    texts: [{ id: "t", text: "inside" }],
  });
  assert.deepEqual(details.ui.spec.elements.s.children, ["m", "c"]);
  assert.deepEqual(details.ui.spec.elements.c.children, ["t"]);
});

test("a valid spec is left as it is", () => {
  const spec = {
    root: "s",
    elements: {
      s: { type: "Stack", props: {}, children: ["t"] },
      t: { type: "Text", props: { text: "x" }, children: [] },
    },
  };
  const result = normalizeUiTopology(spec);
  assert.equal(result.spec, spec);
  assert.deepEqual(result.repairs, []);
});

test("a child of two unrelated containers is rejected with both named", async () => {
  await assert.rejects(
    callAsHarness({
      root: "s",
      stacks: [{ id: "s", children: ["b", "c"] }],
      cards: [
        { id: "b", children: ["m"] },
        { id: "c", children: ["m"] },
      ],
      metrics: [{ id: "m", label: "T1", value: 1 }],
    }),
    /more than one parent[\s\S]*"m" is a child of both "b", "c", and neither contains the other/,
  );
});

test("cycles, missing ids, a parented root and leaf children are not repaired", async () => {
  const base = { metrics: [{ id: "m", label: "T1", value: 1 }] };
  await assert.rejects(
    callAsHarness({ ...base, root: "a", stacks: [{ id: "a", children: ["b", "m"] }], cards: [{ id: "b", children: ["a"] }] }),
    /cycle/,
  );
  // A cycle among orphans is not attached either.
  await assert.rejects(
    callAsHarness({
      ...base,
      root: "m",
      stacks: [{ id: "x", children: ["y"] }],
      cards: [{ id: "y", children: ["x"] }],
    }),
    /render_ui spec is invalid/,
  );
  await assert.rejects(
    callAsHarness({ ...base, root: "s", stacks: [{ id: "s", children: ["m", "nope"] }], texts: [{ id: "o", text: "x" }] }),
    /nope/,
  );
  await assert.rejects(
    callAsHarness({ ...base, root: "s", stacks: [{ id: "s", children: ["m"] }, { id: "p", children: ["s"] }] }),
    /the root "s" is listed as a child of "p"/,
  );
  const leafChildren = normalizeUiTopology({
    root: "s",
    elements: {
      s: { type: "Stack", props: {}, children: [] },
      m: { type: "Metric", props: { label: "T1", value: 1 }, children: ["s"] },
      o: { type: "Text", props: { text: "x" }, children: [] },
    },
  });
  assert.deepEqual(leafChildren.repairs, []);
});

test("repairs never hide invalid props, links, duplicate ids or limits", async () => {
  const orphanText = [{ id: "o", text: "x" }];
  await assert.rejects(
    callAsHarness({ root: "s", stacks: [{ id: "s", children: [] }], metrics: [{ id: "m", label: "T1", value: "" }], texts: orphanText }),
    /elements\.m \(Metric\) props: value/,
  );
  await assert.rejects(
    callAsHarness({ root: "s", stacks: [{ id: "s", children: [] }], links: [{ id: "l", label: "x", href: "https://evil.example" }] }),
    /render_ui spec is invalid/,
  );
  await assert.rejects(
    callAsHarness({ root: "s", stacks: [{ id: "s", children: [] }], texts: [{ id: "s", text: "x" }] }),
    /element id "s" is used by another element/,
  );

  // A vertical root without room for the orphans is wrapped instead.
  const placed = Array.from({ length: UI_SPEC_LIMITS.maxChildren - 2 }, (_, i) => ({ id: `p${i}`, text: "x" }));
  const extra = Array.from({ length: 3 }, (_, i) => ({ id: `o${i}`, text: "x" }));
  const wrapped = await callAsHarness({
    root: "s",
    stacks: [{ id: "s", children: placed.map((t) => t.id) }],
    texts: [...placed, ...extra],
  });
  assert.equal(wrapped.details.ui.spec.root, "ui-root");
  assert.deepEqual(wrapped.details.ui.spec.elements["ui-root"].children, ["s", "o0", "o1", "o2"]);
  // A wrapper with more children than the limit fails; the orphans are named instead.
  await assert.rejects(
    callAsHarness({
      root: "s",
      stacks: [{ id: "s", direction: "horizontal", children: [] }],
      texts: Array.from({ length: UI_SPEC_LIMITS.maxChildren }, (_, i) => ({ id: `o${i}`, text: "x" })),
    }),
    /not reachable from root/,
  );
  const full = {
    root: "s",
    stacks: [{ id: "s", direction: "horizontal", children: [] }],
    texts: Array.from({ length: UI_SPEC_LIMITS.maxElements - 1 }, (_, i) => ({ id: `o${i}`, text: "x" })),
  };
  await assert.rejects(callAsHarness(full), /not reachable from root/);

  // Wrapping must not push the tree past the depth limit.
  const stacks = Array.from({ length: UI_SPEC_LIMITS.maxDepth }, (_, i) => ({
    id: `d${i}`,
    direction: "horizontal",
    children: i < UI_SPEC_LIMITS.maxDepth - 1 ? [`d${i + 1}`] : [],
  }));
  await assert.rejects(
    callAsHarness({ root: "d0", stacks, texts: orphanText }),
    /not reachable from root/,
  );
  // Without the orphan, the same tree is within the limit.
  await callAsHarness({ root: "d0", stacks });
});

test("the stored and chat-side validation still rejects the unrepaired shapes", () => {
  const spec = {
    root: "s",
    elements: {
      s: { type: "Stack", props: {}, children: ["f", "t"] },
      f: { type: "Card", props: {}, children: ["t"] },
      t: { type: "Text", props: { text: "x" }, children: [] },
      a: { type: "Alert", props: { tone: "info", message: "y" }, children: [] },
    },
  };
  assert.equal(validateUiSpec(spec).ok, false);
  assert.equal(uiBlockFromDetails({ ui: { version: 1, spec, fallback: "x" } }), undefined);
});

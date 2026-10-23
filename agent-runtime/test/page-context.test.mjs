import assert from "node:assert/strict";
import { test } from "node:test";

import {
  buildPageContextSection,
  buildProposeCodeEditTool,
  MAX_PAGE_CODE_CHARS,
  parsePageContext,
} from "../src/page-context.ts";

test("a page context is taken only in the shape the API sends", () => {
  assert.equal(parsePageContext(undefined), undefined);
  assert.equal(parsePageContext({ title: "no path" }), undefined);
  assert.deepEqual(parsePageContext({ path: "/chip", title: "Chip" }), { path: "/chip", title: "Chip" });
  assert.deepEqual(
    parsePageContext({ path: "/workflow/t1", flow: { name: "t1", chip_id: "64Qv3", code: "x = 1\n", dirty: true } }),
    { path: "/workflow/t1", flow: { name: "t1", chipId: "64Qv3", code: "x = 1\n", dirty: true } },
  );
  // A flow without code is just a page.
  assert.deepEqual(parsePageContext({ path: "/workflow/t1", flow: { name: "t1" } }), { path: "/workflow/t1" });
});

test("the section names the page, and on the editor carries the code and the edit rule", () => {
  assert.equal(buildPageContextSection(undefined), undefined);
  assert.match(buildPageContextSection({ path: "/chip", title: "Chip 64Qv3" }), /looking at the QDash page "Chip 64Qv3" \(\/chip\)/);
  const section = buildPageContextSection({
    path: "/workflow/t1",
    flow: { name: "t1", chipId: "64Qv3", code: "from prefect import flow\n", dirty: true },
  });
  assert.match(section, /flow `t1` \(chip 64Qv3\) open in the Workflow editor, with unsaved changes/);
  assert.match(section, /```python\nfrom prefect import flow\n```/);
  assert.match(section, /call `propose_code_edit` with the complete new file/);
  assert.match(section, /do not use qdash_save_flow for this flow unless they ask/);
  const long = buildPageContextSection({ path: "/w", flow: { name: "w", code: "x".repeat(MAX_PAGE_CODE_CHARS + 10) } });
  assert.match(long, /cut: the flow is longer than/);
});

test("the edit tool ends the turn with the proposal in its details", async () => {
  const tool = buildProposeCodeEditTool({ name: "t1", chipId: "chip1", code: "" }, "/workflow/t1");
  assert.equal(tool.name, "propose_code_edit");
  const result = await tool.execute({ summary: "Add T2", code: "new code" }, {}, {});
  assert.deepEqual(result.details, { edit: { summary: "Add T2", code: "new code", flowName: "t1", chipId: "chip1", pagePath: "/workflow/t1" } });
  assert.deepEqual(result.control, { terminate: true });
  assert.match(result.output[0].text, /shown to the user as a diff/);
});

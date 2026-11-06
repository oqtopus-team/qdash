import assert from "node:assert/strict";
import { test } from "node:test";

import { extractToolGuide } from "../src/tool-guide.ts";

const SKILL = `---
name: qdash
---

# QDash

Intro line.

## Preferred tools

1. \`qdash_config_info\` — check profile names.
2. Prefer dedicated read-only tools:
   - \`qdash_list_chips\`, \`qdash_get_default_chip\`
   - \`qdash_create_forum_image_reply\` for confirmed uploads
3. Use agent calibration workflow tools when asked:
   - \`qdash_create_agent_session\`
   - \`qdash_submit_agent_action\`
4. \`qdash_raw_get\` — read-only GET endpoints not covered by \`qdash_query\`.
   - \`qdash_preview_forum_image_reply\`, then \`qdash_create_forum_image_reply\` for uploads

## Session context

/qdash-use-profile <profile>
`;

test("keeps only the Preferred tools section", () => {
  const guide = extractToolGuide(SKILL, ["qdash_config_info", "qdash_list_chips"]);
  assert.match(guide, /qdash_config_info/);
  assert.doesNotMatch(guide, /Session context|qdash-use-profile|# QDash|Intro line/);
});

test("drops tools the runtime does not expose, and list items left empty", () => {
  const guide = extractToolGuide(SKILL, [
    "qdash_config_info",
    "qdash_list_chips",
    "qdash_get_default_chip",
  ]);
  assert.match(guide, /`qdash_list_chips`, `qdash_get_default_chip`$/m);
  assert.doesNotMatch(guide, /forum_image|raw_get|agent_session|submit_agent_action/);
  // "3. Use agent calibration workflow tools" has no children left.
  assert.doesNotMatch(guide, /agent calibration workflow/);
});

test("drops an explanatory line when one of its tools is unavailable", () => {
  const guide = extractToolGuide(SKILL, [
    "qdash_list_chips",
    "qdash_query",
    "qdash_preview_forum_image_reply",
  ]);
  assert.doesNotMatch(guide, /raw_get|read-only GET|preview_forum_image_reply|then .* for uploads/);
  assert.match(guide, /`qdash_list_chips`$/m);
});

test("removes a single unavailable name from a comma-separated list", () => {
  const guide = extractToolGuide(SKILL, ["qdash_get_default_chip"]);
  assert.match(guide, /- `qdash_get_default_chip`$/m);
  assert.doesNotMatch(guide, /qdash_list_chips/);
});

test("returns null without the section or without any usable line", () => {
  assert.equal(extractToolGuide("# No guide here\n", ["qdash_list_chips"]), null);
  assert.equal(extractToolGuide(SKILL, []), null);
});

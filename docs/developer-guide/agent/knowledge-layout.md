# Agent Knowledge Layout

Keep task facts, agent procedures, and host behavior in separate sources so both supported hosts
use the same calibration knowledge.

| Content | Source |
| --- | --- |
| Task background and labeled examples | `config/task-knowledge`, a checkout of the [task-knowledge repository](https://github.com/qiqb-osaka/qdash-task-knowledge) |
| Tools, routing, and calibration procedures | `packages/pi-qdash/extensions/` and `packages/pi-qdash/skills/` |
| Web chat behavior and host context | `agent-runtime/src/prompt.ts` |

## Rules

- Put physics and expected plots in the task's `task.md`, not in prompts or tool skills.
- Keep the task-knowledge template, headings, and identity fields unchanged; its generator
  produces the versioned `task-knowledge.json` read by the API.
- Put shared tool policy in `packages/pi-qdash/extensions/lib/qdash-guidance.ts`. The runtime's
  `tool-guide.ts` adapts it to the tools offered by that host.
- Keep web-only instructions out of pi-qdash skills, which also serve pi CLI.
- Repository `.agents/skills/` helps developers edit QDash; it is not distributed to Agent sessions.

## Change knowledge

Test a draft through [AI Evaluations](../../user-guide/ai-evaluations.md), then propose and merge
changes into the knowledge repository's `main` branch. Configure
[repository access](../../user-guide/setup/ai.md#apply-ai-changes), then run `task knowledge-pull`.
Without `KNOWLEDGE_REPO_URL`, the command skips the update.

Before pulling, copy any local work outside `config/task-knowledge`. The command resets tracked
files to `origin/main`, discarding local edits; a failed fetch or reset deletes and reclones the checkout.

For tool procedures, edit the bundled skill, run `task ci-pi-packages` and
`task ci-agent-runtime`, and rebuild the runtime. Sessions record skill name, version, and hash.

## Chat prompts

`agent-runtime/src/prompt.ts` defines runtime prompts.
`src/qdash/agent/prompts/task_chat.py` builds a task chat's opening message.
`src/qdash/datamodel/task_knowledge.py` derives task references on read, keeping old documents
consistent with current interpretation.

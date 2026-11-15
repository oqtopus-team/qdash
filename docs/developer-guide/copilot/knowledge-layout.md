# Copilot Knowledge Layout

Copilot's behaviour comes from three kinds of knowledge that live in three places. QDash owns the tools and product behaviour; task knowledge comes from a separate repository.

| Kind | Examples | Home | How QDash gets it |
| --- | --- | --- | --- |
| Facts about calibration tasks | Background per task (`task.md` with a fixed template: intro, Expected plot, Common failures, Parameters to extract; laid out by calibtasks package) and expert-labeled example plots | [qdash-task-knowledge](https://github.com/qiqb-osaka/qdash-task-knowledge), cloned into `config/task-knowledge` | The repository's `generate.py` builds a versioned `task-knowledge.json` whose contract is `task-knowledge.schema.json` (figures by path, not embedded); the API serves it to the chat prompt, the evaluation reference, and the `qdash_get_task_knowledge` tool. The Knowledge page shows it read-only. |
| Tools and procedures | Tool definitions, "which tool for which question", diagnosis workflows, agent-session workflows | `packages/pi-qdash/` (`extensions/`, `skills/`) | Included from the same QDash checkout in the Agent Runtime image |
| Product behaviour | Persona, approval cards, `ask_user`, output language, turn budgets, model catalog | This repository | `agent-runtime/src/prompt.ts`, `config/copilot/*.yaml` |

The API derives the evaluation reference from `task.md`; do not maintain a second copy.
Write **Expected plot**, **Common failures**, and **Parameters to extract** as criteria that
can be applied to a figure. [Calibration Evaluation](./evaluation.md) defines the derivation
and maps the reference to the six questions. Labeled examples supply `status`, `suggested_range`,
and `parameters` for in-context evaluation.

`task.md` and the example files use YAML frontmatter for machine-readable fields. A task declares
`type: qdash.calibration-task`, `profile: qdash-calibration/v1`, its `name`, and its `category`;
an example declares `type: qdash.calibration-example`, the same profile, and its labels. The
Markdown body remains the reviewable scientific explanation. The generator accepts legacy
`index.md` and bullet metadata while older drafts are migrated, but new content uses frontmatter.

The frontmatter may also carry `next_actions`, the table an autonomous plan follows: for
each status the evaluation can report (`SUCCESS` and one code per `## Common failures` bullet,
derived as [Calibration Evaluation](./evaluation.md) describes), an `action` of `continue`,
`retry`, `run_task` with a `task`, or `request_human`, with optional `overrides`, a
`suggested_range_parameter`, and a `note`. The generator rejects a key the task never reports,
and the API serves the table as `next_actions` on `GET /tasks/{name}/knowledge` while
`TaskKnowledge.next_action_problems` reports a stale key. A `## Recovery` section holds the
prose behind the table for the planner and the reviewer. Neither the frontmatter nor that section
reaches the evaluation prompt, which reads only the intro, the expected plot, the common failures,
and the parameters to extract.

Skills ship with the tools they name; task physics has one source shared by chat, evaluation,
and standalone pi. QDash-only interaction rules stay in the runtime prompt.

## Rules

- Do not put physics or expected-result descriptions into a skill or into `prompt.ts`. Add them to the task's `task.md` in qdash-task-knowledge (intro, Expected plot, Common failures, Parameters to extract) and have the skill say "read the task knowledge for X". A validated plot with its diagnosis goes under `examples/` as a demonstration.
- Do not put pi-qdash tool names into `prompt.ts`. The tool routing guide is the "Preferred tools" section of the pi-qdash `qdash` skill; the runtime reads it at startup, keeps only the tools it exposes, and inlines it into the system prompt (`agent-runtime/src/tool-guide.ts`). The rest of that skill and the other skills stay behind `read_skill`.
- Do not add QDash-only instructions to a pi-qdash skill. pi CLI users get the same skills without the QDash UI.
- The distribution source for agent skills is pi-qdash. Skills under this repository's `.agents/skills/` are for agents editing QDash's own code, not for sessions, and are never recorded.
- Update tool skills in `packages/pi-qdash/skills/` and rebuild the runtime; update task knowledge through the checkout under `config/task-knowledge`. Agent sessions record the skill name, version, and hash they ran with.

## Chat prompts

The Pi Agent Runtime is the only chat backend. Its system prompt lives in `agent-runtime/src/prompt.ts`; the opening message of a chat about a task result is rendered by `src/qdash/copilot/prompts/task_chat.py`.

## Implementation Files

| File | Role |
| --- | --- |
| `agent-runtime/src/prompt.ts` | Chat and analysis system prompts |
| `agent-runtime/src/tool-guide.ts` | Extracts the tool routing guide from the pi-qdash `qdash` skill |
| `agent-runtime/src/skill-tool.ts` | `read_skill`, which serves the pi-qdash skills to the model |
| `agent-runtime/src/allowed-tools.ts` | Which pi-qdash tools the runtime exposes |
| `src/qdash/datamodel/task_knowledge.py` | Loads `task-knowledge.json` |
| `config/copilot/chat.yaml`, `config/copilot/evaluation.yaml` | Planner models; evaluation model and scoring thresholds |

# Copilot Knowledge Layout

Copilot's behaviour comes from three kinds of knowledge that live in three places. QDash consumes the first two at pinned versions and owns only the third.

| Kind | Examples | Home | How QDash gets it |
| --- | --- | --- | --- |
| Facts about calibration tasks | Background per task (`task.md` with a fixed template: intro, Expected plot, Common failures, Parameters to extract; laid out by calibtasks package) and expert-labeled example plots | [qdash-task-knowledge](https://github.com/qiqb-osaka/qdash-task-knowledge), cloned into `config/task-knowledge` | The repository's `generate.py` builds a versioned `task-knowledge.json` whose contract is `task-knowledge.schema.json` (figures by path, not embedded); the API serves it to the chat prompt, the evaluation reference, and the `qdash_get_task_knowledge` tool. The Knowledge page shows it read-only. |
| Tools and procedures | Tool definitions, "which tool for which question", diagnosis workflows, agent-session workflows | [pi-qdash](https://github.com/oqtopus-team/pi-qdash) (`extensions/`, `skills/`) | Installed into the Agent Runtime image at a pinned version (`agent-runtime/Dockerfile`) |
| Product behaviour | Persona, approval cards, `ask_user`, output language, turn budgets, model catalog | This repository | `agent-runtime/src/prompt.ts`, `config/copilot/*.yaml` |

The evaluation reference is derived from `task.md`, not written separately: the API's `GET /tasks/{name}/knowledge` serves `reference` with the background (`This is a <task> experiment: <intro>. <Expected plot prose>`), the parameters to extract (one `float` per bullet under **Parameters to extract**), and the status criteria (`SUCCESS` from the "A good result" sentence, then one `UPPER_SNAKE` code per bullet under **Common failures**, with the text up to the first `;` as its criterion). The evaluation model is asked the six QCalEval questions against exactly that, so write those sections as criteria a reader could apply to a plot; the derivation rules and the question each part fills are in [Calibration Evaluation](./evaluation.md). An example under `examples/` may carry `status`, `suggested_range` and `parameters` next to its `outcome`; those are what the in-context demonstrations show for the status, significance and extraction questions.

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

The split follows what changes together. A skill that names `qdash_list_cooldowns` must ship with the version of pi-qdash that defines that tool, so skills live next to the tools. Task physics is the same whether it is read by Ask AI in the analysis sidebar, the chat, or a pi CLI user, so it has one source that every consumer queries. The approval-card flow exists only in the QDash UI, so its instructions stay here.

## Rules

- Do not put physics or expected-result descriptions into a skill or into `prompt.ts`. Add them to the task's `task.md` in qdash-task-knowledge (intro, Expected plot, Common failures, Parameters to extract) and have the skill say "read the task knowledge for X". A validated plot with its diagnosis goes under `examples/` as a demonstration.
- Do not put pi-qdash tool names into `prompt.ts`. The tool routing guide is the "Preferred tools" section of the pi-qdash `qdash` skill; the runtime reads it at startup, keeps only the tools it exposes, and inlines it into the system prompt (`agent-runtime/src/tool-guide.ts`). The rest of that skill and the other skills stay behind `read_skill`.
- Do not add QDash-only instructions to a pi-qdash skill. pi CLI users get the same skills without the QDash UI.
- The distribution source for agent skills is pi-qdash. Skills under this repository's `.agents/skills/` are for agents editing QDash's own code, not for sessions, and are never recorded.
- Updating knowledge means bumping a version: the pi-qdash version in `agent-runtime/Dockerfile`, or the task-knowledge checkout under `config/task-knowledge`. Agent sessions record the skill name, version, and hash they ran with.

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

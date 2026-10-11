# Copilot Knowledge Layout

Copilot's behaviour comes from three kinds of knowledge that live in three places. QDash consumes the first two at pinned versions and owns only the third.

| Kind | Examples | Home | How QDash gets it |
| --- | --- | --- | --- |
| Facts about calibration tasks | Background, expected plot, the four outcomes as they look on this plot, parameters to extract, expert-labeled example plots | [qdash-task-knowledge](https://github.com/qiqb-osaka/qdash-task-knowledge), cloned into `config/task-knowledge` | The repository's `generate.py` builds `task-knowledge.json` (figures by path, not embedded); the API serves it to the chat prompt, the evaluation reference, and the `qdash_get_task_knowledge` tool. The Knowledge page edits it. |
| Tools and procedures | Tool definitions, "which tool for which question", diagnosis workflows, agent-session workflows | [pi-qdash](https://github.com/oqtopus-team/pi-qdash) (`extensions/`, `skills/`) | Installed into the Agent Runtime image at a pinned version (`agent-runtime/Dockerfile`) |
| Product behaviour | Persona, approval cards, `ask_user`, output language, turn budgets, model catalog | This repository | `agent-runtime/src/prompt.ts`, `config/copilot/*.yaml` |

The split follows what changes together. A skill that names `qdash_list_cooldowns` must ship with the version of pi-qdash that defines that tool, so skills live next to the tools. Task physics is the same whether it is read by Ask AI in the analysis sidebar, the chat, or a pi CLI user, so it has one source that every consumer queries. The approval-card flow exists only in the QDash UI, so its instructions stay here.

## Rules

- Do not put physics or expected-result descriptions into a skill or into `prompt.ts`. Add them to the task's `index.md` in qdash-task-knowledge (background, expected plot, outcomes, parameters) and have the skill say "read the task knowledge for X". A validated plot with its diagnosis goes under `examples/` as a demonstration.
- Do not put pi-qdash tool names into `prompt.ts`. The tool routing guide is the "Preferred tools" section of the pi-qdash `qdash` skill; the runtime reads it at startup, keeps only the tools it exposes, and inlines it into the system prompt (`agent-runtime/src/tool-guide.ts`). The rest of that skill and the other skills stay behind `read_skill`.
- Do not add QDash-only instructions to a pi-qdash skill. pi CLI users get the same skills without the QDash UI.
- The distribution source for agent skills is pi-qdash. `.codex/skills/qdash` is a development helper for agents that have no pi extension and is not what sessions record.
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

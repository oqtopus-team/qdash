# Copilot Knowledge Layout

Copilot's behaviour comes from three kinds of knowledge that live in three places. QDash consumes the first two at pinned versions and owns only the third.

| Kind | Examples | Home | How QDash gets it |
| --- | --- | --- | --- |
| Facts about calibration tasks | Physics, expected curve, failure modes, postmortem cases | [qdash-task-knowledge](https://github.com/oqtopus-team/qdash-task-knowledge), cloned into `config/task-knowledge` | `task knowledge` generates `task-knowledge.json`; the API serves it to the analysis prompts and to the `qdash_get_task_knowledge` tool |
| Tools and procedures | Tool definitions, "which tool for which question", diagnosis workflows, agent-session workflows | [pi-qdash](https://github.com/oqtopus-team/pi-qdash) (`extensions/`, `skills/`) | Installed into the Agent Runtime image at a pinned version (`agent-runtime/Dockerfile`) |
| Product behaviour | Persona, approval cards, `ask_user`, output language, turn budgets, model catalog | This repository | `agent-runtime/src/prompt.ts`, `config/copilot/*.yaml` |

The split follows what changes together. A skill that names `qdash_list_cooldowns` must ship with the version of pi-qdash that defines that tool, so skills live next to the tools. Task physics is the same whether it is read by Ask AI in the analysis sidebar, the chat, or a pi CLI user, so it has one source that every consumer queries. The approval-card flow exists only in the QDash UI, so its instructions stay here.

## Rules

- Do not put physics or expected-result descriptions into a skill or into `prompt.ts`. Add them to the task's `index.md` in qdash-task-knowledge and have the skill say "read the task knowledge for X".
- Do not put pi-qdash tool names into `prompt.ts`. The tool routing guide is the "Preferred tools" section of the pi-qdash `qdash` skill; the runtime reads it at startup, keeps only the tools it exposes, and inlines it into the system prompt (`agent-runtime/src/tool-guide.ts`). The rest of that skill and the other skills stay behind `read_skill`.
- Do not add QDash-only instructions to a pi-qdash skill. pi CLI users get the same skills without the QDash UI.
- The distribution source for agent skills is pi-qdash. `.codex/skills/qdash` is a development helper for agents that have no pi extension and is not what sessions record.
- Updating knowledge means bumping a version: the pi-qdash version in `agent-runtime/Dockerfile`, or the task-knowledge checkout under `config/task-knowledge`. Agent sessions record the skill name, version, and hash they ran with.

## Chat prompts

The Pi Agent Runtime is the chat backend this layout describes. `src/qdash/copilot/prompts/chat.py` holds the system prompt of the earlier LiteLLM chat backend (`copilot_backend: litellm`); it is kept for that backend and does not receive new guidance. Analysis prompts in `src/qdash/copilot/prompts/analysis.py` are shared by both backends.

## Implementation Files

| File | Role |
| --- | --- |
| `agent-runtime/src/prompt.ts` | Chat and analysis system prompts |
| `agent-runtime/src/tool-guide.ts` | Extracts the tool routing guide from the pi-qdash `qdash` skill |
| `agent-runtime/src/skill-tool.ts` | `read_skill`, which serves the pi-qdash skills to the model |
| `agent-runtime/src/allowed-tools.ts` | Which pi-qdash tools the runtime exposes |
| `src/qdash/datamodel/task_knowledge.py` | Loads `task-knowledge.json` |
| `config/copilot/chat.yaml`, `config/copilot/review.yaml` | Models and scoring thresholds |

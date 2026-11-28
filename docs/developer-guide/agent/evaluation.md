# Calibration Evaluation

An evaluation records a model's judgment of a task-result figure. A record holds evidence,
answers, and human verdicts; a run groups records for comparison.

## Responsibilities

| Part | Responsibility |
| --- | --- |
| Task-knowledge repository | Task reference and labeled examples |
| pi-qdash | Fetch authoritative task-result evidence |
| pi-qcaleval | Ask the six QCalEval questions and parse answers |
| Agent Runtime | Hydrate context and return a reproducible record |
| QDash API | Permissions, persistence, runs, and human verdicts |

## The protocol

Each QCalEval question is a separate single-turn request with background, experiment context,
question, and figure. Keep the question protocol in pi-qcaleval; hosts must not replace it with
an improvised summary. Chat, single-result, and bulk evaluation leave the same record shape.

## From task knowledge to the prompt

The API derives the task reference from `task.md` on each read and serves labeled examples.
The runtime fetches them as the requesting user. Optional examples apply only to questions that
support them. Missing knowledge or examples is recorded rather than invented.

Prompt preview builds the same questions without a model call. A knowledge draft replaces the
reference only for the requested evaluation; it does not alter shared task knowledge.
See the [draft procedure](../../user-guide/ai-evaluations.md#try-a-knowledge-change-before-proposing-it).

## The record

Preserve exact prompts, model/evaluator identity, evidence references and hashes, knowledge
identity, requested versus used examples, answers, and human review. A rerun creates another
snapshot; it does not overwrite the earlier judgment.

## Comparing runs

Join records by target and show whether they evaluated the same task result. Differences in
model, knowledge, mode, or examples are part of the comparison. Model assessment is evidence,
not permission to update calibration values.

## Changing it

Change task facts in the knowledge repository, shared hydration in pi-qdash, question/parsing
logic in pi-qcaleval, and persistence in the API. Run `task ci-pi-packages`,
`task ci-agent-runtime`, and affected evaluation API tests. Verify preview/runtime parity,
missing evidence, project access, and record reproducibility.

## Implementation Files

| File | Responsibility |
| --- | --- |
| `agent-runtime/src/evaluate.ts` | Evaluation and prompt preview |
| `agent-runtime/src/knowledge-context.ts` | Authorized knowledge fetching |
| `agent-runtime/src/durable-tools.ts` | Host metadata on tool results |
| `src/qdash/datamodel/evaluation.py` | Stored record shape |
| `src/qdash/datamodel/task_knowledge.py` | Reference derivation |

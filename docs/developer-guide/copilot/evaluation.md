# Calibration Evaluation

An evaluation is a recorded judgement of one task result's figure by the calibration evaluation
model, which answers the six questions of the QCalEval benchmark against the task's reference
from the knowledge repository. This page is the mechanism; the procedures are in
[AI Evaluations](../../user-guide/ai-evaluations.md).

Two words recur. A **record** is one evaluation: what the model was given, what it answered,
and what a person said about it. A **run** is a set of records requested together, which is the
unit of comparison.

## Responsibilities

| Part | Owns | Where |
| --- | --- | --- |
| Task knowledge | The reference and the labeled example plots of each task | [qdash-task-knowledge](https://github.com/qiqb-osaka/qdash-task-knowledge), checked out at `config/task-knowledge` |
| pi-qdash | `qdash_build_qcal_evidence`: one task result as evidence | Pinned in `agent-runtime/Dockerfile` |
| pi-qcaleval | `qcal_evaluate`: question templates, model calls, answer parsing, `dry_run` | Pinned in `agent-runtime/Dockerfile`; a checkout under `agent-runtime/extensions/` replaces it |
| Agent Runtime | One evaluation: the two tools, the reference and examples filled in as the user, the record, the prompt preview | `agent-runtime/src/evaluate.ts`, `knowledge-context.ts` |
| API and UI | Runs: selection, background execution, storage, verdicts, chat recording, comparison | `src/qdash/api/services/evaluation_service.py`, `ui/src/components/features/evaluations/` |

Nothing about the physics of a task lives in QDash code. The reference is derived from the
task's `index.md`, the demonstrations are its `examples/`, and the question templates belong to
the extension. QDash decides what else reaches the model (the context) and keeps the records.

## The protocol

pi-qcaleval asks the questions the way the benchmark ([arXiv 2604.25884](https://arxiv.org/abs/2604.25884))
and the Ising-Calibration training data do. Each question is one single-turn request with no
system prompt: the background, an `Experiment context:` line, and the question template with the
figure at its `<image>` position. The six requests go out at once. A request that fails is sent
once more; an answer that arrived is never asked again, whatever it says. The model decodes
greedily (`temperature: 0.0` in `config/copilot/evaluation.yaml`), so the same plot and prompt
give the same diagnosis and two runs are comparable.

| Key | Question | Filled from the reference | Parsed answer |
| --- | --- | --- | --- |
| `technical_description` | Describe the figure in JSON | nothing, not even the background | `{plot_type, x_axis, y_axis, main_features}`, or the text |
| `experimental_conclusion` | Classify the outcome | background | `classification`: expected, suboptimal, anomalous, apparatus; `reason` |
| `experimental_significance` | What does this result imply | background; `guidance` bullets; the tool's optional `question` argument as one more point | text |
| `fit_reliability` | Is the fit reliable for parameter extraction | background | `assessment`: reliable, unreliable, no_fit; `reason` |
| `parameter_extraction` | Extract parameters in JSON | background; `parameters` as the JSON schema to report | the object, or the text |
| `calibration_diagnosis` | Determine the experiment status | background; `statuses` as the decision criteria, SUCCESS first; `range_format` for the suggested range | `status`, `suggested_range`, `notes` |

The diagnosis adds `success`: the status is `SUCCESS`, or, when the status question was not
asked, the outcome is `expected`. Every answer is kept as returned in `answers`, next to the
parsed reading. Without criteria the templates fall back to generic guidance, ask for whatever
parameters the plot determines, and offer `SUCCESS`, `SUBOPTIMAL`, `NO_SIGNAL` and `ANOMALOUS`.

## From task knowledge to the prompt

`GET /tasks/{task_name}/knowledge` serves a task's `reference`, derived on every read from its
`index.md` by `derive_reference` (`src/qdash/datamodel/task_knowledge.py`), and its examples
with figure bytes inlined. The runtime fetches it as the requesting user and passes it to
`qcal_evaluate` as `knowledge` (the background) and `criteria` (the rest).

| `index.md` | Becomes | Rule |
| --- | --- | --- |
| Intro, first paragraph | background | `This is a <task> experiment: <intro>. <expected plot>` |
| `## Expected plot`, first paragraph | background, and the `SUCCESS` criterion | The sentence beginning `A good result`, with that prefix dropped; the first sentence when there is none |
| `## Common failures`, each bullet | one status code and its criterion | Title and criterion split at the first ` — `, ` – ` or `: `; see below |
| `## Parameters to extract`, each `name: description` bullet | one entry of the extraction schema | `name` must be an identifier; the type is `int` or `true \| false` when the description says so, else `float` |

A failure bullet's title becomes its code: parentheses are dropped and the rest is upper-snake-
cased, so `Short T1 (<20 μs)` gives `SHORT_T1`. Its criterion is the text after the separator up
to the first `;`. A bullet without a separator uses its first four words as the title and its
whole text as the criterion. A code seen twice keeps its first criterion. The model reads the
criterion verbatim as its decision rule, so write it as a test a reader could apply to the plot.

`guidance` and `range_format` are not derived from `index.md`. The significance question uses
the extension's default guidance, and the suggested-range format comes from the result's sweep
(below). Only prose paragraphs feed the background, so a section that opens with a bullet list
contributes nothing to it. A task with knowledge but no derivable background (an old-format
entry) gets its whole rendered text instead, cut at 6000 characters, with no criteria.

The reference is hashed for the record (`knowledge_sha256` over the background and the
criteria), so two evaluations made against different versions of a task's knowledge are told
apart on the compare page.

### Labeled examples

In-context evaluation (`with_examples`) shows the task's `examples/` before the figure, laid out
as the benchmark's few-shot split and only for the three questions that use them:

| Question | Shows | From the example's |
| --- | --- | --- |
| `experimental_significance` | every example's figure and analysis under `Scenario "<title>":` | diagnosis paragraph |
| `parameter_extraction` | the first example that has values, as `Extracted parameters:` | `parameters` |
| `calibration_diagnosis` | every example's figure with `Status:` and `Suggested range:` | `status`, `suggested_range` |

`examplesOf` (`agent-runtime/src/knowledge-context.ts`) walks the examples in the repository's
order and keeps one per `status`; a second example with the same status is dropped, and an
example without a status is kept for the analysis demonstration. An example without a figure or
without any label is skipped. Selection stops at six examples or six figures. An example labeled
only with `outcome` and `verdict` therefore reaches the significance question alone; the status
and extraction demonstrations need `status`, `suggested_range` and `parameters`, as the
knowledge repository's README describes.

### Previewing the prompts

`GET /tasks/{task_name}/evaluation-prompts?with_examples=&knowledge_draft_id=` returns the six
prompts a task's knowledge, or a knowledge draft of that task, turns into, built without a
figure or a model call. The API forwards it to the
runtime's `POST /evaluation-prompts`, which fetches the reference and examples exactly as an
evaluation does and runs `qcal_evaluate` with `dry_run: true`, so the templates stay in the
extension. The response carries the prompts by question (`[figure]` where an image goes), the
model that would judge, the reference's size and hash, and the examples used. The Knowledge
page shows it (`ui/src/components/features/task-knowledge/EvaluationPromptPreview.tsx`) and
refetches it when the task's file is saved.

## What the model is told besides the plot

The direct path builds the `context` line from the evidence tool's structured details, not from
its text (`evidenceContext` in `evaluate.ts`): the task, its target and status; the sweep the
plot was taken over (`sweeps`, which pi-qdash reads from the recorded run parameters with their
units: start, stop, points, step); the other run settings (shots, interval); and the task
message. The fitted output parameters and the calibration inputs stay out: the model is meant
to read the plot, and the benchmark gives it nothing but the plot and the background. The sweep
also supplies the status question's suggested-range format
(`(<min time_range>, <max time_range>) [ns]`) when the task's knowledge states none, so the
model answers a corrective range in the swept parameter's unit.

The evidence tool returns the result's figure. `max_figures` (default 1, at most 4) asks for
more; the last figure is the one judged and earlier ones are shown as references.

## Entry points and runs

Every judgement the evaluation model makes becomes an `evaluation` document under an
`evaluation_run`, whatever asked for it.

| Trigger | Who | How |
| --- | --- | --- |
| `bulk` | Chip page | `POST /evaluations/runs` with a task and a chip, a day, or a list of task results |
| `single` | A task result's **Ask AI** | The same route with one task result |
| `chat` | The planner, during a chat | Recorded from the `qcal_evaluate` tool result; see below |

A bulk request selects the latest evaluable result of the task per qubit or coupling of the
chip, or the results of the day. The run stores one pending record per task result and executes
them in the background of the API worker as the requesting user, a few at a time
(`EVALUATION_CONCURRENCY`, default 2). Entities without an evaluable result (no result, no
figure, still running) are reported as skipped. A run interrupted by an API restart keeps its
unfinished records as pending; request it again rather than resuming it.

Each record is produced by the runtime's `POST /evaluate` in one of two modes:

- `direct` (the default) runs `qdash_build_qcal_evidence` and then `qcal_evaluate` as such,
  with the reference and examples filled in as above. Fast and reproducible.
- `planner` opens a throwaway conversation on the chat's planner model, tells it to summarise
  the result and judge its figure (`plannerInstruction`), and reads the record off the
  `qcal_evaluate` result it produced. The planner writes its own context and may pass its own
  reference; what it did and answered is stored next to the record.

The two modes differ in what reaches the evaluation model, which is exactly what the stored
records make comparable.

A chat is recorded the same way: when the planner calls `qcal_evaluate`, the durable tool
wrapper stamps a `host` record (the figure and reference the runtime filled in) on the result,
the runtime's `tool_end` event carries it, and the API files it as a run of one with the
planner's final answer. A figure no tool fetched, such as a user attachment, is not recorded.

### Knowledge drafts

A knowledge draft is one task's knowledge directory, uploaded as a zip, that a run reads in
place of the shared `task-knowledge.json`. It lets a person measure an edit to `index.md` or
`examples/` before proposing it to the knowledge repository, without changing what any other
user's chat or evaluation reads.

`POST /evaluations/knowledge-drafts` (multipart, editor role) stores the zip under
`<calib_data>/projects/<project_id>/knowledge-drafts/<sha256>/`: the upload as `draft.zip`, the
uploader and the generator's warnings in `draft.json`, and the extracted directory under
`task/<TaskName>/`. The SHA-256 of the zip is the draft id, so the same zip uploaded twice is the
same draft, and a draft never changes. The store rejects a zip that is not one task directory,
holds paths outside it, links or files other than `.md`, `.png`, `.jpg`, `.jpeg` and `.webp`, or
exceeds `MAX_ZIP_BYTES` (20 MB), `MAX_EXTRACTED_BYTES` (50 MB, counted while extracting) or
`MAX_ENTRIES` (200).

The directory is parsed by the knowledge repository's own `generate.py`: `parse_task_dir`
loads it from the `config/task-knowledge` checkout and calls its `_parse_task`, so a draft reads
exactly as the published entry would, warnings included. The resulting `TaskKnowledge` resolves
its figures inside the draft directory. Without the checkout's `generate.py` the upload answers
503.

`GET /evaluations/knowledge-drafts/{id}/archive` returns `draft.zip` byte for byte under its
uploaded file name, so the knowledge a run read can be downloaded from the run's page and
uploaded again as the same draft. `task_archive` builds the zip a draft starts from: the published task directory under one
folder, holding only the file types a draft accepts, so a download uploads again unchanged.

A run names the draft with `knowledge_draft_id`; the run stores it with the zip's file name
(`knowledge_draft_name`). The API refuses a draft of another task and a draft in planner mode,
because the planner's `qcal_evaluate` call is filled with the shared knowledge. The runtime
fetches `GET /evaluations/knowledge-drafts/{id}/knowledge`, which has the shape of
`GET /tasks/{name}/knowledge`, once per evaluation (`draftKnowledge` in `evaluate.ts`) and uses
it for both the reference and the examples. A draft the API does not serve fails the evaluation
at the `knowledge` stage instead of letting it run without a reference. Drafts are scoped to
their project and are not deleted.

### The record

`src/qdash/datamodel/evaluation.py` is the shape; `_input_from_record` and
`_output_from_record` in the evaluation service fill it from the runtime's answer.

| Part | Holds |
| --- | --- |
| `input` | The context, the exact prompt (`[figure]` marks an image) and system prompt, the run's question (only runs made before knowledge drafts have one), the reference's size and hash, the figures by hash, the examples by id and figure hash |
| `output` | The model (`provider/modelId`, `fallback` when no calibration VLM was configured), the parsed diagnosis, the raw answer, every answer as returned, the questions asked, `attempts`, `stop_reason`, each call's duration and output tokens, the total duration and token usage |
| `evaluator` | The extension that judged: package name, version, `checkout` or `package`, the checkout commit |
| `planner` | In planner mode: the planner's model, answer, tool calls and duration |
| `verdict` | A person's **Agree** or **Disagree** with a note, who and when |

`complete` and `missing_keys` are derived from the diagnosis over the questions asked on every
load, so records stored before those fields existed are judged the same way. A run's summary
adds its wall time and the completed records' model time added up, so runs are weighed on cost
as well as outcome.

### Comparing runs

A run is a snapshot. The same selection evaluated again after a change to the extension, the
model, the mode, the examples setting or the task's reference yields a second run of the same
shape. `/evaluations/compare?a=&b=` joins two runs in the browser
(`evaluationCompare.ts`): settings side by side with the differing ones flagged, totals, and one
row per entity (joined by qid, noting whether both judged the same task result) with each side's
fit quality, success and verdict. There is no compare API.

## Changing it

**A task's reference.** Edit the task's `index.md` in the knowledge repository, within its
template; the Knowledge page's **Download zip** (`GET /tasks/{task_name}/knowledge/archive`)
gives the published directory to start from. Evaluate the edited directory as a knowledge draft
against a run on the shared knowledge before proposing it; the **Evaluation prompts** panel
previews the shared reference or a dropped draft. The Knowledge page does not write: updating a
deployment means merging into the repository and moving the `config/task-knowledge` checkout
(`task knowledge-pull`).

**A demonstration.** Add `examples/<slug>.md` with a figure, `outcome`, and the QCalEval labels
(`status` from the task's criteria, `suggested_range`, `parameters`), then regenerate
`task-knowledge.json` with the repository's `generate.py`. Label the success case too: the
status question shows one example per status.

**A question template or its parsing.** Change pi-qcaleval. A checkout under
`agent-runtime/extensions/` is loaded in place of the pinned package (restart the runtime; the
startup log names it), and every record says which one judged. Release it and bump the pin in
`agent-runtime/Dockerfile`.

**The context or the evidence.** `evidenceContext` and `sweepRangeFormat` in `evaluate.ts` decide
what the context says; the evidence itself is pi-qdash's tool.

**The model.** Declare it in `config/copilot/evaluation.yaml`. pi-qcaleval takes, in order, an
explicit `model` argument or `QCALEVAL_MODEL`; else the first configured model whose id matches
`Ising-Calibration`; else the conversation's own model when it accepts images, with
`fallback: true` on the record. Each request carries the background, one question and the
figures, at most four per evaluation (`MAX_IMAGES`), so an evaluation fits a 16k-token
deployment.

Tests: `agent-runtime/test/evaluate.test.mjs` and `knowledge-context.test.mjs` (prompt fill,
context, examples, preview), `tests/qdash/datamodel/test_task_knowledge_registry.py`
(reference derivation), `tests/qdash/api/routers/test_evaluation.py` and
`tests/qdash/api/services/test_pi_evaluation_service.py` (runs and the runtime call),
`tests/qdash/api/services/test_knowledge_draft_service.py` (draft storage and validation),
`ui/src/components/features/evaluations/__tests__/` (display, prompt profile, compare).

## Implementation Files

| File | Role |
| --- | --- |
| `agent-runtime/src/evaluate.ts` | `evaluateTask`, `previewEvaluationPrompts`, `evidenceContext`, `plannerInstruction`, `hostRecord`, the record |
| `agent-runtime/src/knowledge-context.ts` | Fetching the reference, examples and knowledge drafts as the user; `examplesOf` |
| `agent-runtime/src/durable-tools.ts` | Stamps the `host` record on every `qcal_evaluate` result, which chat recording and planner mode read |
| `agent-runtime/src/server.ts` | `POST /evaluate`, `POST /evaluation-prompts` |
| `src/qdash/datamodel/task_knowledge.py` | `derive_reference`, `KnowledgeExample`, `parse_task_dir` |
| `src/qdash/datamodel/evaluation.py` | The evaluation record |
| `src/qdash/api/services/evaluation_service.py` | Runs: selection, background execution, chat recording, verdicts |
| `src/qdash/api/services/pi_evaluation_service.py` | The runtime calls |
| `src/qdash/api/services/knowledge_draft_service.py` | `KnowledgeDraftStore`: storing, validating and reading knowledge drafts; `task_archive` |
| `src/qdash/api/routers/evaluation.py`, `routers/task.py` | `/evaluations/*` (runs, knowledge drafts), `/tasks/{task_name}/knowledge`, `/tasks/{task_name}/knowledge/archive`, `/tasks/{task_name}/evaluation-prompts` |
| `ui/src/components/features/evaluations/` | Request modal with the knowledge draft picker (`KnowledgeDraftPicker.tsx`), run list and detail, compare page |
| `ui/src/components/features/task-knowledge/EvaluationPromptPreview.tsx` | The Knowledge page's prompt panel, with a draft drop for editors |
| `config/copilot/evaluation.yaml` | The evaluation model and its decoding settings |

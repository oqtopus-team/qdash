# pi-qcaleval

A [pi](https://github.com/badlogic/pi-mono) extension that sends superconducting
qubit calibration plots to a dedicated calibration-evaluation VLM and returns a
structured diagnosis. The default model is
[NVIDIA Ising-Calibration](https://build.nvidia.com/nvidia/ising-calibration-1.5-31b/modelcard)
served by vLLM, and the questions are the ones it was trained and benchmarked
on: the six questions of
[QCalEval](https://arxiv.org/abs/2604.25884), asked the way the benchmark asks
them.

The planner model keeps the conversation; `qcal_evaluate` is the tool it calls
whenever a calibration figure needs a fit-quality judgement, parameter
extraction, or a status verdict. The extension has no QDash dependency, so it
works from the pi CLI and from the QDash Copilot runtime alike.

## Tool

`qcal_evaluate(context, question?, task_name?, knowledge?, criteria?, images?, max_images?, use_examples?, examples?, questions?)`
asks the evaluation model six questions, each in its own single-turn request
(no system prompt), with the figure at the position the benchmark's templates
put it, and returns the parsed answers as `details.diagnosis`:

| key | the benchmark's question | parsed answer |
| --- | --- | --- |
| `technical_description` | Q1 Describe the figure in JSON | `{plot_type, x_axis, y_axis, main_features}`, or the text when not JSON |
| `experimental_conclusion` | Q2 Classify the outcome | `{classification: expected \| suboptimal \| anomalous \| apparatus, reason}` |
| `experimental_significance` | Q3 What does this result imply | text |
| `fit_reliability` | Q4 Is the fit reliable for extraction | `{assessment: reliable \| unreliable \| no_fit, reason}` |
| `parameter_extraction` | Q5 Extract parameters in JSON | the object, or the text when not JSON |
| `calibration_diagnosis` | Q6 Determine the status | `{status: CODE, suggested_range, notes}` |

plus `success`: whether the status is `SUCCESS` (or, when the status question
was not asked, whether the outcome is `expected`). `details.answers` keeps every
answer as returned, `details.questions` the questions asked, `details.prompt`
every user turn the model received (with `[figure]` where an image was), and
`details.calls` each question's call with its duration, stop reason, and input
and output tokens. A call that fails is retried once, as the benchmark retries API
failures; nothing is re-asked for its content. Questions that got no answer are
listed in `details.missing_keys`. `questions` asks a subset. `dry_run` builds
the prompts and returns them (`details.prompts` by question, `details.prompt`
as one text) without asking the model, so a host can show what a task's
reference and examples turn into; the figure may be omitted then.

`knowledge` is the experiment background the benchmark prepends to Q2–Q6: a few
sentences on what the experiment sweeps and what a successful result looks like.
`criteria` fills the family-specific parts of the templates: `guidance` (the
points Q3 should explain), `parameters` (the Q5 schema, name to type),
`statuses` (the Q6 decision criteria, code to criterion, `SUCCESS` first) and
`range_format`. A host that keeps such knowledge per task fills both in from
`task_name`, so the planner only names the task. Without them the templates use
generic guidance, ask for whatever parameters the plot determines, and offer
`SUCCESS` / `SUBOPTIMAL` / `NO_SIGNAL` / `ANOMALOUS`.

`context` is what the background cannot know (the task, the target, a swept
range); the model reads values off the plot, so do not pass fitted results. A
`question` is added to Q3 as one more point to address.

`images` are base64 image blocks. A host may fill them in from the most recent
figures of the conversation, so the planner does not have to pass image bytes;
`max_images` (default 1, up to 4) says how many of the newest figures to supply,
for example 2 when an expected reference figure precedes the measured result.
The last figure is the one judged; earlier ones are shown as references.

### Labeled examples (in-context)

With `use_examples`, the host supplies `examples`: each is one or more figures
with the answers an expert validated (`scenario`, `analysis`, `parameters`,
`status`, `suggested_range`). They are laid out as the benchmark's few-shot
split lays them out, examples first and the query figure last, and only for the
three questions the benchmark uses them for: Q3 shows each example's
`analysis` under `Scenario "<scenario>":`, Q5 shows one example's
`parameters`, Q6 shows each example's `Status:` and `Suggested range:`. Up to
six examples and six example figures are shown; the rest are dropped in order.

## Configuration

No setting is required. The evaluation model is resolved in this order:

1. the call's `model` (`provider/modelId`), when the host offers several evaluation models, then
   `QCALEVAL_MODEL`, an explicit override for pi CLI use;
2. a configured calibration VLM, recognised by its id (`Ising-Calibration`);
3. the conversation's own model, when it accepts images. The result is then
   marked `fallback: true` in `details`, so a host without an Ising deployment
   still gets a diagnosis from the vision model it already runs.

The output budget per answer follows the model's `maxTokens` (at most 4096). The
benchmark decodes greedily; set the model's temperature to 0 for reproducible
answers.

The provider must be declared in pi's `models.json` with its base URL and
credential, for example:

```json
{
  "providers": {
    "vllm": {
      "baseUrl": "https://llm.example/v1",
      "api": "openai-completions",
      "apiKey": "$VLLM_API_KEY",
      "models": [{ "id": "nvidia/Ising-Calibration-1.5-31B-NVFP4", "contextWindow": 16384, "maxTokens": 2048, "input": ["text", "image"] }]
    }
  }
}
```

Each request carries one plot, the background and one question, so an
evaluation fits comfortably in a 16k-token deployment; the six requests run at
once.

## Installation

```bash
pi install npm:@orangekame3/pi-qcaleval
```

Releases use QDash tags `pi-qcaleval/vX.Y.Z` and publish to npm as `latest`.
Changes to the pi packages on QDash's `develop` branch publish `beta` prereleases
(`npm:@orangekame3/pi-qcaleval@beta`).

## Development

From the QDash repository root:

```bash
bun install --frozen-lockfile
task ci-pi-packages
task ci-agent-runtime
pi -e ./packages/pi-qcaleval
```

The QDash runtime includes this package from the same checkout. Rebuild it after
editing with `docker compose up -d --build agent-runtime`. See the
[package release guide](../../docs/developer-guide/copilot/packages.md).

## License

Apache-2.0

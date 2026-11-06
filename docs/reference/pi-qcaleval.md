# pi-qcaleval

`@oqtopus-team/pi-qcaleval` evaluates calibration figures independently of QDash.
For the QDash host integration, see [Calibration Evaluation](../developer-guide/copilot/evaluation.md).

## Tool

`qcal_evaluate` accepts calibration context and figures and returns a parsed diagnosis.

| Input | Contract |
| --- | --- |
| `context` | Task, target, and sweep context; omit fitted results. |
| `question` | Extra point for the significance question. |
| `task_name` | Task name for a host to resolve knowledge. |
| `knowledge` | Experiment background for questions Q2–Q6. |
| `criteria` | `guidance`, `parameters`, `statuses`, and `range_format` for the question templates. |
| `images` | Base64 figure blocks; the last figure is judged and earlier figures are references. |
| `max_images` | Number of newest figures to include; default 1, maximum 4. |
| `use_examples`, `examples` | Include labeled examples in Q3, Q5, and Q6; maximum six examples and six example figures. |
| `questions` | Subset of the six questions to ask. |
| `model` | Explicit evaluation model as `provider/modelId`. |
| `dry_run` | Return prompt previews without a model call; figures can be omitted. |

## Parsed answers

| Key | Question | Parsed answer |
| --- | --- | --- |
| `technical_description` | Q1 Describe the figure in JSON | `{plot_type, x_axis, y_axis, main_features}`, or the text when not JSON |
| `experimental_conclusion` | Q2 Classify the outcome | `{classification: expected \| suboptimal \| anomalous \| apparatus, reason}` |
| `experimental_significance` | Q3 What does this result imply | text |
| `fit_reliability` | Q4 Is the fit reliable for extraction | `{assessment: reliable \| unreliable \| no_fit, reason}` |
| `parameter_extraction` | Q5 Extract parameters in JSON | the object, or the text when not JSON |
| `calibration_diagnosis` | Q6 Determine the status | `{status: CODE, suggested_range, notes}` |

| Output | Contract |
| --- | --- |
| `success` | True for status `SUCCESS`, or for outcome `expected` when Q6 was not asked. |
| `details.diagnosis` | Parsed answers keyed by question. |
| `details.answers` | Answers exactly as returned by the model. |
| `details.questions` | Questions asked. |
| `details.prompt` | User turns sent to the model, with `[figure]` at image positions. |
| `details.calls` | Per-question duration, stop reason, and token counts. |
| `details.missing_keys` | Questions with no answer after one retry of a failed call. |
| `details.prompts` | Per-question prompts from `dry_run`. |

Without task-specific `criteria`, the status choices are `SUCCESS`, `SUBOPTIMAL`,
`NO_SIGNAL`, and `ANOMALOUS`.

## Labeled examples

| Field | Use |
| --- | --- |
| `scenario`, `analysis` | Q3 significance examples. |
| `parameters` | Q5 extraction example; the first example with values is used. |
| `status`, `suggested_range` | Q6 diagnosis examples. |
| Figures | Up to six example figures precede the query figure. |

## Configuration

| Priority | Model source |
| --- | --- |
| 1 | Call's `model` (`provider/modelId`), then `QCALEVAL_MODEL`. |
| 2 | Configured model whose ID contains `Ising-Calibration`. |
| 3 | Conversation model with image input; sets `details.fallback: true`. |

| Setting | Limit |
| --- | --- |
| Output tokens | Model's `maxTokens`, capped at 4096 per answer. |
| Temperature | Set to 0 for reproducible answers. |
| Provider | Declare the model, base URL, and credential in pi's `models.json`. See [Pi Extension Design](../developer-guide/copilot/extensions.md#pi-qcaleval). |

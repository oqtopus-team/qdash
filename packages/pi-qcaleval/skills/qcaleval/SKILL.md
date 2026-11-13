---
name: qcaleval
description: Evaluate superconducting qubit calibration plots with the dedicated calibration VLM through the pi-qcaleval extension. Use when a calibration figure (Rabi, Ramsey, chevron, T1/T2, readout, spectroscopy, two-qubit tune-up) needs an outcome classification, a fit-reliability judgement, parameter extraction, or a status verdict.
---

<!-- Whether a calibration loop continues after an evaluation is the host's policy. This skill describes the tool, not when to stop. -->

# Calibration plot evaluation

`qcal_evaluate` sends a plot to a calibration-evaluation model (NVIDIA
Ising-Calibration by default) and asks it the six QCalEval questions, each in
its own request. The diagnosis it returns has one entry per question:
`technical_description`, `experimental_conclusion` (outcome: expected /
suboptimal / anomalous / apparatus), `experimental_significance`,
`fit_reliability` (reliable / unreliable / no_fit), `parameter_extraction`,
and `calibration_diagnosis` (a status code, a suggested range, notes), plus
`success` (the status is SUCCESS).

## Preferred tools

- `qcal_evaluate`: judge one or more calibration plots. Give `context` for what
  the background cannot know: the task name, the target (qubit or coupling),
  the swept range. Do not put fitted values in it; the model reads the plot.
  Add `question` when a specific point matters (for example "is the chevron
  centred on the current frequency?"); it is added to the significance question.
- Pass `task_name` whenever you know the task (for example `CheckRabi`): the
  host then supplies the experiment background and the task's criteria (the
  parameters to extract, the status codes), which is more reliable than a
  summary you write yourself.
- When the conversation holds an expected reference figure followed by the
  measured result (a task review opens this way), pass `max_images: 2` and say
  in `context` that the first figure is the reference and the last the
  measurement. The host then supplies both; the default is the newest figure only.
- Pass `questions` to ask a subset, for example `["calibration_diagnosis"]`
  when only the status matters.
- Pass `model` (`provider/modelId`) only when the user names one of the
  configured evaluation models; otherwise the configured calibration VLM judges.
- Pass `dry_run: true` to see the prompts the model would get (per question)
  without asking it, for example when the user wants to check a task's
  reference before judging.

## Labeled examples (in-context)

- When the user asks to judge a plot against the labeled reference examples
  (in-context examples, few-shot), pass `use_examples: true` with `task_name`.
  The host supplies its expert-labeled example plots for that task, and the
  model sees them before the figure to judge, in the layout of the QCalEval
  few-shot benchmark: each example's status for the status question, each
  example's analysis for the significance question, one example's values for
  parameter extraction. Leave it off otherwise.

## How to use the result

- Treat the diagnosis as the evaluation of record; reason on top of it instead
  of re-judging the plot yourself.
- Report the status, the fit reliability and the outcome verbatim, then the
  extracted parameters and the suggested range when there is one.
- When the status is not SUCCESS, say what the notes and the outcome reason
  identified as the cause before proposing a next step.
- The model only sees the plot, the background and the context you pass. If a
  conclusion needs data that is not in the plot (previous values, device
  limits), fetch it and include it in `context`.

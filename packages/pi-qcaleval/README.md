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

## Installation

```bash
pi install npm:@oqtopus-team/pi-qcaleval
```

Use `npm:@oqtopus-team/pi-qcaleval@beta` for prereleases. Existing pi CLI users
should remove `@orangekame3/pi-qcaleval` before installing the new package to avoid
loading both extensions. Historical releases remain available under the old name.

## Documentation and development

The [pi-qcaleval reference](https://oqtopus-team.github.io/qdash/reference/pi-qcaleval)
lists tool inputs, outputs, model selection, and the six questions. The
[pi extension design guide](https://oqtopus-team.github.io/qdash/developer-guide/copilot/extensions)
shows standalone model configuration. The
[QDash evaluation guide](https://oqtopus-team.github.io/qdash/developer-guide/copilot/evaluation)
explains how the runtime supplies figures and task knowledge.

This package lives in the [QDash monorepo](https://github.com/oqtopus-team/qdash/tree/develop/packages/pi-qcaleval).
Follow the [package development and release guide](https://oqtopus-team.github.io/qdash/developer-guide/copilot/packages)
for workspace setup, checks, local pi CLI testing, and independent npm releases.
Report issues in [QDash](https://github.com/oqtopus-team/qdash/issues).

## License

Apache-2.0

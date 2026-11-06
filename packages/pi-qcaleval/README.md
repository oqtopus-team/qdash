<!-- markdownlint-disable MD041 -->
![OQTOPUS logo](https://raw.githubusercontent.com/oqtopus-team/qdash/develop/docs/public/images/oqtopus-logo.png)

# pi-qcaleval

[![CI](https://github.com/oqtopus-team/qdash/actions/workflows/publish-typescript-packages.yml/badge.svg)](https://github.com/oqtopus-team/qdash/actions/workflows/publish-typescript-packages.yml)
[![npm version](https://img.shields.io/npm/v/%40oqtopus-team%2Fpi-qcaleval.svg)](https://www.npmjs.com/package/@oqtopus-team/pi-qcaleval)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![slack](https://img.shields.io/badge/slack-OQTOPUS-pink.svg?logo=slack&style=plastic)](https://join.slack.com/t/oqtopus/shared_invite/zt-3bpjb7yc3-Vg8IYSMY1m5wV3DR~TMSnw)

`@oqtopus-team/pi-qcaleval` is a [pi](https://github.com/badlogic/pi-mono)
extension that sends superconducting qubit calibration plots to a dedicated
calibration-evaluation VLM and returns a
structured diagnosis. The default model is
[NVIDIA Ising-Calibration](https://build.nvidia.com/nvidia/ising-calibration-1.5-31b/modelcard)
served by vLLM, and the questions are the ones it was trained and benchmarked
on: the six questions of
[QCalEval](https://arxiv.org/abs/2604.25884), asked the way the benchmark asks
them.

The extension has no QDash dependency, so it works from the pi CLI and from the
QDash Copilot runtime alike.

## Features

- **Dedicated evaluation tool**: `qcal_evaluate` judges fit quality, extracts
  parameters, and returns a calibration status while the planner model keeps the
  conversation.
- **Structured diagnosis**: ask all six QCalEval questions or select a subset, with
  parsed answers and per-question call details.
- **Model selection**: use an explicit evaluation model, `QCALEVAL_MODEL`, a configured
  Ising-Calibration model, or an image-capable conversation model.

## Installation

Install pi first if needed:

```bash
npm install -g --ignore-scripts @earendil-works/pi-coding-agent
```

Install the extension:

```bash
pi install npm:@oqtopus-team/pi-qcaleval
```

Or try it without installing:

```bash
pi -e npm:@oqtopus-team/pi-qcaleval
```

The package declares Node.js 20 or later and is tested with Node.js 24 and pi 1.4.0.
Use the `beta` dist-tag to try changes merged into QDash's `develop` branch:

```bash
pi install npm:@oqtopus-team/pi-qcaleval@beta
```

Existing pi CLI users should remove `@orangekame3/pi-qcaleval` before installing
the new package to avoid loading both extensions. Historical releases remain
available under the old name.

## Quick start

Configure an image-capable evaluation model in pi's `models.json`, then ask pi to
evaluate a calibration figure. The planner calls `qcal_evaluate` with the figure
and calibration context. See the [pi-qcaleval reference](https://oqtopus-team.github.io/qdash/reference/pi-qcaleval)
for model configuration and tool inputs.

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
Open pull requests against QDash's `develop` branch and report bugs in
[QDash issues](https://github.com/oqtopus-team/qdash/issues).

## Contact

Open a [QDash issue](https://github.com/oqtopus-team/qdash/issues) or email us:

- [oqtopus-team[at]googlegroups.com](mailto:oqtopus-team[at]googlegroups.com)

## License

pi-qcaleval is released under the [Apache License 2.0](./LICENSE).

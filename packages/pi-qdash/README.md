<!-- markdownlint-disable MD041 -->
![OQTOPUS logo](https://raw.githubusercontent.com/oqtopus-team/qdash/develop/packages/pi-qdash/docs/asset/oqtopus-logo.png)

# pi-qdash

[![CI](https://github.com/oqtopus-team/qdash/actions/workflows/publish-typescript-packages.yml/badge.svg)](https://github.com/oqtopus-team/qdash/actions/workflows/publish-typescript-packages.yml)
[![npm version](https://img.shields.io/npm/v/%40oqtopus-team%2Fpi-qdash.svg)](https://www.npmjs.com/package/@oqtopus-team/pi-qdash)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![slack](https://img.shields.io/badge/slack-OQTOPUS-pink.svg?logo=slack&style=plastic)](https://join.slack.com/t/oqtopus/shared_invite/zt-3bpjb7yc3-Vg8IYSMY1m5wV3DR~TMSnw)

## Overview

**pi-qdash** is a [pi](https://github.com/badlogic/pi-mono) extension for querying [QDash](https://github.com/oqtopus-team/qdash), the large-scale QPU calibration platform in the OQTOPUS ecosystem, directly from the pi coding agent.

It uses [`@oqtopus-team/qdash-client`](https://www.npmjs.com/package/@oqtopus-team/qdash-client) and reuses existing `QDASH_*` environment variables or profiles from `~/.config/qdash/config.ini` / `$XDG_CONFIG_HOME/qdash/config.ini`.

## Key Features

- **Read-only investigation**: dedicated tools to inspect chips, qubits, couplings, calibration task results, task knowledge (`qdash_get_task_knowledge`), executions, and Forum posts. Secrets are redacted from tool output.
- **Dashboards and insights**: compact dashboards, triage overviews, target-level incident reports, degradation reports, and wiring insights.
- **Agent calibration workflow**: create agent sessions, submit and track agent actions, and commit/apply calibration candidates. Write operations are approval-gated.
- **Calibration pipelines**: compose a declarative pipeline spec from QDash's step catalog (`qdash_get_pipeline_catalog`), validate it (`qdash_plan_pipeline`), and run it as one execution (`qdash_run_pipeline`, approval-gated).
- **Figures**: fetch calibration PNG/JSON figures and render them in the interactive TUI.
- **Generic timeseries comparison**: inspect and align arbitrary QDash parameters/targets with explicitly mapped local CSV sensor columns, reuse schema-validated investigation presets, and report correlations plus optional shared-period/phase evidence without hard-coded metrics or schemas.
- **Forum integration**: read Forum posts, publish task-result evidence, and upload locally generated analysis images to replies.

## Installation

Install pi first if needed:

```bash
npm install -g --ignore-scripts @earendil-works/pi-coding-agent
```

Install the published extension:

```bash
pi install npm:@oqtopus-team/pi-qdash
```

Or try it without installing:

```bash
pi -e npm:@oqtopus-team/pi-qdash
```

The package declares Node.js 20 or later and is tested with Node.js 24 and pi 1.4.0.
Published releases pin the matching `@oqtopus-team/qdash-client` version.
Use the `beta` dist-tag to try changes merged into QDash's `develop` branch:

```bash
pi install npm:@oqtopus-team/pi-qdash@beta
```

## Quick Start

In interactive pi, set up the session context first:

```text
/qdash-setup <profile> <chip_id>
/qdash-dashboard
```

See the documentation below for the full tool and command reference.

## Documentation and development

The [tool, command, and skill reference](https://oqtopus-team.github.io/qdash/reference/pi-qdash)
describes the extension's capabilities. The
[pi extension design guide](https://oqtopus-team.github.io/qdash/developer-guide/copilot/extensions)
explains where to add tools, safety gates, and domain reasoning.

Development takes place in the [QDash monorepo](https://github.com/oqtopus-team/qdash/tree/develop/packages/pi-qdash).
Follow the [package development and release guide](https://oqtopus-team.github.io/qdash/developer-guide/copilot/packages)
for workspace setup, checks, local pi CLI testing, and independent npm releases.
Open pull requests against QDash's `develop` branch and report bugs in
[QDash issues](https://github.com/oqtopus-team/qdash/issues).

## Citation

Citation information is available in the [CITATION](https://github.com/oqtopus-team/qdash/blob/develop/packages/pi-qdash/CITATION.cff) file.

## Contact

You can contact us by creating an issue in this repository or by email:

- [oqtopus-team[at]googlegroups.com](mailto:oqtopus-team[at]googlegroups.com)

## License

pi-qdash is released under the [Apache License 2.0](./LICENSE).

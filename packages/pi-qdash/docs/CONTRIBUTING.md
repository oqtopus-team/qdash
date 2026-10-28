# Contributing

Contribute pi-qdash changes through the [QDash repository](https://github.com/oqtopus-team/qdash).
Report bugs, questions, and feature requests in its issue tracker.

Follow the root `AGENTS.md` and [development guide](./DEVELOPMENT.md).
Create feature branches from `develop`, run `task ci-pi-packages` and
`task ci-agent-runtime`, then run `task check` before pushing. Open PRs against
QDash's `develop` branch with Conventional Commit titles.

The [package release guide](../../../docs/developer-guide/copilot/packages.md)
describes beta and stable npm distribution from QDash. The package keeps its
existing npm name and independent version line.

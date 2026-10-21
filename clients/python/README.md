# qdash-client

`qdash-client` is the Python package for QDash API access. User installation, configuration, API
groups, error handling, and agent examples live in the
[Python client guide](../../docs/reference/clients/python.md).

## Develop the Package

Install the repository package and run its checks from the repository root:

```bash
uv sync --all-groups
task test-client
```

The package has two layers:

| Layer | Responsibility |
| --- | --- |
| `src/qdash/client/services/` | High-level models, configuration, retries, validation, and agent runners |
| `src/qdash/client/rest/` | Generated low-level HTTP transport |

Add application-facing operations to `QDashClient`. Keep raw request and generated transport
details inside the REST layer. Export public classes and response models from
`src/qdash/client/__init__.py`, then cover the behavior in `clients/python/tests/`.

## Publish the Package

PyPI Trusted Publishing publishes `qdash-client` from this repository. The package version is
derived from the repository's `v<version>` release tag; do not edit a version in
`clients/python/pyproject.toml`.

Creating the tag also publishes the TypeScript client and creates the GitHub release:

```bash
git tag v<version>
git push origin v<version>
```

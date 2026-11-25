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

`src/qdash/client/services/models.py` is generated from `docs/oas/openapi.json`; regenerate it
with `task generate` (or `task generate-python-schema` for the models alone) and never edit it by
hand. Keep client-side models that the OpenAPI document does not describe, or that the client
validates more leniently, in `src/qdash/client/services/client_models.py`.

Add application-facing operations to `QDashClient`. Keep raw request and generated transport
details inside the REST layer. Export public classes and response models from
`src/qdash/client/__init__.py`, then cover the behavior in `clients/python/tests/`.

## Publication

The client and SDK share QDash's release version. PyPI Trusted Publishing publishes the client
first, then the SDK. Do not edit a package version manually; see
[package releases](../../docs/developer-guide/agent/packages.md).

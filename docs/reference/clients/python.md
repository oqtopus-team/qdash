# Python Client

`qdash-client` provides typed, high-level access to QDash for scripts, notebooks, exporters, and
agent integrations. It supports Python 3.11 and 3.12.

## Install the Package

```bash
pip install qdash-client
```

The distribution name is `qdash-client`; import it as `qdash.client`.

## Configuration

Use an API token for programmatic access. `QDASH_BASE_URL` is the only required environment
variable; include an API path prefix when the deployment exposes one.

```bash
export QDASH_BASE_URL="https://your-qdash-instance/api"
export QDASH_API_TOKEN="your-api-token"
export QDASH_PROJECT_ID="your-project-id"
```

```python
from qdash.client import QDashClient

client = QDashClient.from_env()
```

The client reads these settings:

| Environment variable | Default | Purpose |
| --- | --- | --- |
| `QDASH_BASE_URL` | Required | QDash API base URL |
| `QDASH_API_TOKEN` | None | Bearer token |
| `QDASH_PROJECT_ID` | None | Active project header |
| `QDASH_CF_ACCESS_CLIENT_ID` | None | Cloudflare Access client ID |
| `QDASH_CF_ACCESS_CLIENT_SECRET` | None | Cloudflare Access client secret |
| `QDASH_TIMEOUT_SECONDS` | `30` | Request timeout |
| `QDASH_MAX_WORKERS` | `4` | Concurrent worker limit |
| `QDASH_RETRY_MAX_ATTEMPTS` | `3` | Maximum attempts for retryable GET requests |
| `QDASH_RETRY_BACKOFF_SECONDS` | `0.2` | Initial retry delay |
| `QDASH_RETRY_MAX_BACKOFF_SECONDS` | `5.0` | Maximum retry delay |
| `QDASH_VERIFY_TLS` | `true` | TLS certificate verification |
| `QDASH_PROXY` | None | HTTP proxy URL |
| `QDASH_USER_AGENT` | Package version | Custom user-agent value |

Legacy deployments can use `QDASH_USERNAME` and the password variable named by
`QDASH_PASSWORD_ENV`, which defaults to `QDASH_PASSWORD`.

Named profiles live in `$XDG_CONFIG_HOME/qdash/config.ini`, or `~/.config/qdash/config.ini` when
`XDG_CONFIG_HOME` is unset:

```ini
[prod]
base_url = https://your-qdash-instance/api
api_token = your-api-token
project_id = your-project-id
timeout_seconds = 30
retry_max_attempts = 3
```

```python
from qdash.client import QDashClient

client = QDashClient.from_profile("prod")
```

`QDashConfig.save()` creates or updates a profile with owner-only permissions (`0600`). Constructing
`QDashClient()` without a configuration loads the `default` profile.

## Call the High-Level API

Close the client after use so its HTTP session is released:

```python
from qdash.client import QDashClient

client = QDashClient.from_profile("prod")
try:
    chip = client.get_default_chip()
    metrics = client.get_chip_metrics(chip.chip_id)
    print(metrics.qubit_metrics)
finally:
    client.close()
```

The high-level client groups operations by domain:

| Domain | Primary methods |
| --- | --- |
| Chips and metrics | `list_chips`, `get_default_chip`, `get_chip_metrics`, `get_metrics_config`, qubit and coupling getters |
| Task results | `list_task_results`, latest-result and history getters, `get_task_result`, notes, exclusion, and re-execution |
| Projects and files | Project getters, file tree and content, validation, and configuration Git operations |
| Issues and knowledge | Issue lifecycle, approved knowledge, and task knowledge operations |
| Flows and executions | Flow templates, save, execute, schedule, wait, and cancel operations |
| Provenance | Entity, lineage, impact, history, statistics, and recent-change operations |
| Agent calibration | Sessions, actions, candidate gates, commits, apply operations, and polling helpers |

Methods return Pydantic models exported from `qdash.client`. Configuration failures raise
`QDashConfigError`; API and transport failures raise subclasses of `QDashApiError`:

| Exception | Condition |
| --- | --- |
| `QDashConfigError` | Missing or invalid local configuration |
| `QDashAuthError` | Missing or rejected authentication |
| `QDashNotFoundError` | HTTP 404 |
| `QDashValidationError` | Invalid request arguments or an unexpected response shape |
| `QDashTransportError` | Network failure, timeout, or another unexpected HTTP status |

Only `list_chips_async`, `get_task_results_timeseries_async`, and `get_metrics_config_async` have
async variants. They use the same `QDashClient` configuration and close their temporary async HTTP
clients after each request. Call `close()` to release the persistent synchronous transport.

## Agent Calibration

`AgentCalibrationRunner` runs one bounded step and `AgentCampaignRunner` runs an approved graph of
steps. Both use `QDashClient` for session policy, execution, candidate validation, commit, and
backend-apply operations.

```python
from qdash.client import AgentCalibrationRunner, QDashClient

client = QDashClient.from_profile("local")
try:
    outcome = AgentCalibrationRunner(client).run_step(
        session_id="SESSION_ID",
        task_name="CheckT1",
        qid="Q00",
        source_execution_id="SOURCE_EXECUTION_ID",
        candidate_parameter="t1",
    )
    print(outcome.transition, outcome.reason)
finally:
    client.close()
```

The runner does not create the approved scope implicitly. Create and review the session first, then
handle `pass`, `retry`, `rollback`, and `human_escalation` as described in
[Agent Calibration](../../user-guide/agent-calibration.md).

## Use the Low-Level Client

`qdash.client.rest` exposes the generated transport for operations that do not yet have a
high-level method. Prefer `QDashClient` when a high-level method exists because it supplies shared
authentication, project headers, retries, response validation, and error mapping.

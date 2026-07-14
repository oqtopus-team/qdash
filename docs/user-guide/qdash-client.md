# QDash Client

The Python package `qdash.client` is a client for reading QDash data from scripts, notebooks, and external automation.

## Installation

Install the client package from PyPI.

```bash
pip install qdash-client
```

The distribution name is `qdash-client`, but the Python import path is `qdash.client`.

```python
from qdash.client import QDashClient
```

## Configuration

Use an API token for programmatic access. The client reads configuration from environment
variables or from a named profile in `config.ini`.

`QDASH_BASE_URL` must point to the API base URL. For local development this is usually
`http://localhost:5715`. If a deployment exposes the API under a prefix, include it in the value,
such as `https://your-qdash-instance/api`.

```bash
export QDASH_BASE_URL="https://your-qdash-instance"
export QDASH_API_TOKEN="your-api-token"
export QDASH_PROJECT_ID="your-project-id"
```

If QDash is behind Cloudflare Access, also set:

```bash
export QDASH_CF_ACCESS_CLIENT_ID="your-client-id"
export QDASH_CF_ACCESS_CLIENT_SECRET="your-client-secret"
```

`QDASH_PROJECT_ID` is only needed when the QDash instance uses project-scoped access. Cloudflare
Access credentials are only needed when QDash is behind Cloudflare Access.

Use `QDashClient.from_env()` when a script should load these variables and fail early if the base
URL is missing.

```python
from qdash.client import QDashClient

client = QDashClient.from_env()
```

The same configuration can be stored in `$XDG_CONFIG_HOME/qdash/config.ini`, or in
`~/.config/qdash/config.ini` when `XDG_CONFIG_HOME` is not set. Profiles are stored as sections in
the file.

```ini
[local]
base_url = http://localhost:5715
api_token = your-local-api-token

[prod]
base_url = https://your-qdash-instance/api
api_token = your-prod-api-token
project_id = your-project-id
cf_access_client_id = your-client-id
cf_access_client_secret = your-client-secret
```

Read a saved profile with `QDashClient.from_profile()`.

```python
from qdash.client import QDashClient

client = QDashClient.from_profile("prod")
```

Create or update a profile from Python with `QDashConfig.save()`.

```python
from qdash.client import QDashConfig

config = QDashConfig(
    base_url="http://localhost:5715",
    api_token="your-api-token",
    project_id=None,
    cf_access_client_id=None,
    cf_access_client_secret=None,
)
saved_path = config.save(profile="local")
print(saved_path)
```

Saved config files use owner-only permissions (`0600`) because they can contain API tokens and
Cloudflare Access secrets.

## Basic Usage

Create a client, call the API, and close the HTTP session when the script exits.
`get_default_chip_id()` returns the latest active chip when one is available, then falls back to the
latest installed chip.

```python
from qdash.client import QDashClient

client = QDashClient.from_env()
try:
    chips = client.list_chips()
    print(f"chips: {chips.total}")

    for chip in chips.chips:
        print(chip.chip_id, chip.activity_status)

    chip_id = client.get_default_chip_id()
    print(f"default chip: {chip_id}")
finally:
    client.close()
```

## Chip Metrics

Use `get_chip_metrics()` to read the dashboard metric payload for a chip.

```python
from qdash.client import QDashClient

client = QDashClient.from_env()
try:
    chip_id = client.get_default_chip_id()
    metrics = client.get_chip_metrics(chip_id)

    print(metrics.chip_id)
    print(f"qubit metric groups: {len(metrics.qubit_metrics)}")
    print(f"coupling metric groups: {len(metrics.coupling_metrics)}")

    for metric_name, values in sorted(metrics.qubit_metrics.items())[:5]:
        entity_ids = ", ".join(sorted(values.keys())[:5])
        print(metric_name, entity_ids)
finally:
    client.close()
```

## Metrics Configuration

`get_metrics_config()` returns the metric metadata used by the QDash dashboard, including display labels and color scale settings.

```python
from qdash.client import QDashClient

client = QDashClient.from_env()
try:
    metrics_config = client.get_metrics_config()

    qubit_metrics = metrics_config.get("qubit_metrics", {})
    coupling_metrics = metrics_config.get("coupling_metrics", {})

    print("Qubit metrics:", sorted(qubit_metrics))
    print("Coupling metrics:", sorted(coupling_metrics))
finally:
    client.close()
```

## Time-Series Data

Use `get_task_results_timeseries()` to read calibrated parameter values for a chip and time range.
Pass ISO 8601 UTC timestamps with a trailing `Z`.

```python
from datetime import UTC, datetime, timedelta

from qdash.client import QDashClient

PARAMETER = "t1"
QID: str | None = None
LOOKBACK_DAYS = 30

client = QDashClient.from_env()
try:
    chip_id = client.get_default_chip_id()
    end_at_value = datetime.now(UTC)
    start_at_value = end_at_value - timedelta(days=LOOKBACK_DAYS)
    start_at = start_at_value.isoformat().replace("+00:00", "Z")
    end_at = end_at_value.isoformat().replace("+00:00", "Z")

    series = client.get_task_results_timeseries(
        chip_id=chip_id,
        parameter=PARAMETER,
        qid=QID,
        start_at=start_at,
        end_at=end_at,
    )

    point_count = sum(len(points) for points in series.data.values())
    print(f"time series: chip={chip_id} parameter={PARAMETER} points={point_count}")

    for qid, points in series.data.items():
        for point in points:
            print(qid, point.parameter_name, point.value, point.calibrated_at)
finally:
    client.close()
```

## Async Usage

The client also exposes async variants for read operations.

```python
import asyncio

from qdash.client import QDashClient, QDashConfig


async def main() -> None:
    config = QDashConfig.from_env()
    client = QDashClient(config)
    try:
        chips = await client.list_chips_async()
        print([chip.chip_id for chip in chips.chips])

        series = await client.get_task_results_timeseries_async(
            chip_id="chip-001",
            parameter="t1",
            start_at="2026-06-01T00:00:00Z",
            end_at="2026-06-08T00:00:00Z",
        )
        print(series.data)
    finally:
        client.close()


asyncio.run(main())
```

## Error Handling

All client API failures inherit from `QDashApiError`. Invalid request parameters raise
`QDashValidationError`, missing resources raise `QDashNotFoundError`, authentication failures raise
`QDashAuthError`, and network or unexpected HTTP failures raise `QDashTransportError`.

```python
from qdash.client import QDashApiError, QDashClient

client = QDashClient.from_env()
try:
    chips = client.list_chips()
    print(chips.total)
except QDashApiError as exc:
    print(exc.status_code, exc)
finally:
    client.close()
```

# Logging

The API uses structured JSON logging with request ID correlation, dual output (stdout + rotating file), and centralized `dictConfig` configuration.

## Configuration

Logging is initialized at application startup in the FastAPI lifespan handler:

```python
# src/qdash/api/db/session.py
from qdash.api.logging_config import setup_logging
setup_logging()
```

The log level is controlled by the `LOG_LEVEL` environment variable (default: `INFO`):

```bash
# In .env or docker compose environment
LOG_LEVEL=DEBUG
```

The configuration lives in `src/qdash/api/logging_config.py` and uses `pythonjsonlogger` for JSON formatting.

### Suppressed Loggers

Third-party loggers are set to `WARNING` to reduce noise:

| Logger | Level |
|--------|-------|
| `uvicorn`, `uvicorn.access`, `uvicorn.error` | WARNING |
| `gunicorn`, `gunicorn.access`, `gunicorn.error` | WARNING |
| `pymongo`, `pymongo.command`, `pymongo.topology`, `pymongo.connection` | WARNING |

## Log Format

Each log entry is a JSON object with the following fields:

| Field | Description | Example |
|-------|-------------|---------|
| `timestamp` | ISO 8601 timestamp | `"2025-12-21 10:30:45,123"` |
| `name` | Logger name (module path) | `"qdash.api.routers.chip"` |
| `level` | Log level | `"INFO"` |
| `message` | Log message | `"Chip data updated"` |
| `request_id` | Correlation ID from middleware | `"a1b2c3d4"` |

Example output:

```json
{"timestamp": "2025-12-21 10:30:45,123", "name": "qdash.api.routers.chip", "level": "INFO", "message": "Chip data updated", "request_id": "a1b2c3d4"}
```

## Request ID

The `RequestIdMiddleware` assigns a unique ID to every incoming HTTP request:

1. If the client sends an `X-Request-ID` header, that value is used
2. Otherwise, a short UUID (8 hex characters) is generated
3. The ID is stored in a `ContextVar` and injected into every log record by `RequestIdFilter`
4. The ID is echoed back in the `X-Request-ID` response header

This allows you to correlate all log entries produced during a single request:

```bash
# Filter Docker console logs for a specific request
docker compose logs --no-log-prefix api | jq 'select(.request_id == "a1b2c3d4")'
```

## Adding Logging to New Modules

Use the standard `logging.getLogger(__name__)` pattern:

```python
import logging

logger = logging.getLogger(__name__)

def some_function():
    logger.info("Processing started", extra={"item_id": "123"})
    # ...
    logger.warning("Unexpected value", extra={"value": value})
```

The `request_id` field is injected automatically by the logging filter. You do not need to add it manually.

## Log File Access

In Docker, the API container writes logs to `/app/logs/api.log` in a named volume:

```yaml
# compose.yaml
volumes:
  - api-logs:/app/logs
```

| Setting | Value |
|---------|-------|
| Docker volume | `api-logs` |
| Container path | `/app/logs/api.log` |
| Max file size | 10 MB |
| Backup count | 5 |
| Rotation | `RotatingFileHandler` (automatic) |

When the log file reaches 10 MB, it is rotated to `api.log.1`, `api.log.2`, etc., keeping up to 5 backups.
Host-side API runs write to `${XDG_STATE_HOME:-$HOME/.local/state}/qdash/logs/api.log`.

## Filtering & Querying

Since logs are JSON, you can use `jq` to filter and query them:

```bash
# All errors
docker compose logs --no-log-prefix api | jq 'select(.level == "ERROR")'

# Logs from a specific module
docker compose logs --no-log-prefix api | jq 'select(.name == "qdash.api.routers.chip")'

# Logs for a specific request ID
docker compose logs --no-log-prefix api | jq 'select(.request_id == "a1b2c3d4")'

# Errors in the last hour (requires GNU date)
docker compose logs --no-log-prefix api | jq --arg since "$(date -d '1 hour ago' '+%Y-%m-%d %H:%M')" \
  'select(.level == "ERROR" and .timestamp >= $since)'

# Count log entries by level
docker compose logs --no-log-prefix api | jq -s 'group_by(.level) | map({level: .[0].level, count: length})'
```

For live log streaming:

```bash
# Stream console logs via docker compose
docker compose logs -f api

# Stream and filter the host-side log file
tail -f "${XDG_STATE_HOME:-$HOME/.local/state}/qdash/logs/api.log" | jq 'select(.level == "ERROR")'
```

## Implementation Files

- `src/qdash/api/logging_config.py` — centralized `setup_logging()`
- `src/qdash/api/middleware/request_id.py` — request ID middleware and filter
- `src/qdash/api/main.py` — middleware registration
- `src/qdash/api/db/session.py` — lifespan handler calling `setup_logging()`

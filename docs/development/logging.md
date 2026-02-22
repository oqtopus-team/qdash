# Logging

This document describes the structured logging infrastructure for the QDash API.

## Overview

The API uses structured JSON logging with the following features:

- **JSON format** for machine-readable log entries
- **Request ID correlation** to trace all logs from a single HTTP request
- **Dual output** to both console (stdout) and a rotating log file
- **Centralized configuration** via Python `dictConfig`

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
# Filter logs for a specific request
jq 'select(.request_id == "a1b2c3d4")' logs/api/api.log
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

In Docker, the API container writes logs to `/app/logs/api.log`, which is mounted to the host:

```yaml
# compose.yaml
volumes:
  - ./logs/api:/app/logs
```

| Setting | Value |
|---------|-------|
| Host path | `./logs/api/api.log` |
| Container path | `/app/logs/api.log` |
| Max file size | 10 MB |
| Backup count | 5 |
| Rotation | `RotatingFileHandler` (automatic) |

When the log file reaches 10 MB, it is rotated to `api.log.1`, `api.log.2`, etc., keeping up to 5 backups.

## Filtering & Querying

Since logs are JSON, you can use `jq` to filter and query them:

```bash
# All errors
jq 'select(.level == "ERROR")' logs/api/api.log

# Logs from a specific module
jq 'select(.name == "qdash.api.routers.chip")' logs/api/api.log

# Logs for a specific request ID
jq 'select(.request_id == "a1b2c3d4")' logs/api/api.log

# Errors in the last hour (requires GNU date)
jq --arg since "$(date -d '1 hour ago' '+%Y-%m-%d %H:%M')" \
  'select(.level == "ERROR" and .timestamp >= $since)' logs/api/api.log

# Count log entries by level
jq -s 'group_by(.level) | map({level: .[0].level, count: length})' logs/api/api.log
```

For live log streaming:

```bash
# Stream console logs via docker compose
docker compose logs -f api

# Stream and filter the log file
tail -f logs/api/api.log | jq 'select(.level == "ERROR")'
```

## Best Practices

1. **Use `logging.getLogger(__name__)`** — never instantiate loggers with hard-coded names
2. **Use structured `extra` fields** — pass context as `extra={"key": value}` instead of string interpolation
3. **Choose the right level**:
   - `DEBUG` — detailed diagnostic info (disabled in production)
   - `INFO` — routine operations (request handled, task completed)
   - `WARNING` — unexpected but recoverable situations
   - `ERROR` — failures that need attention
   - `CRITICAL` — system-level failures
4. **Never log secrets** — do not log passwords, tokens, API keys, or PII
5. **Keep messages concise** — use extra fields for variable data rather than long format strings
6. **Do not configure logging in individual modules** — all configuration is centralized in `logging_config.py`

## Related Files

| File | Description |
|------|-------------|
| `src/qdash/api/logging_config.py` | Centralized logging configuration (`setup_logging()`) |
| `src/qdash/api/middleware/request_id.py` | Request ID middleware and logging filter |
| `src/qdash/api/main.py` | Middleware registration (`app.add_middleware(RequestIdMiddleware)`) |
| `src/qdash/api/db/session.py` | Lifespan handler that calls `setup_logging()` |
| `compose.yaml` | Volume mount for log files (`./logs/api:/app/logs`) |

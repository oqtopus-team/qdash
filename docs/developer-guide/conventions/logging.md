# Logging

The API writes structured JSON logs with a request ID to stdout and a rotating file.

## Configuration

`src/qdash/api/logging_config.py` initializes logging at startup. `LOG_LEVEL` defaults to `INFO`;
noisy server and database loggers use `WARNING`.

Each record includes timestamp, logger name, level, message, and `request_id`.
`src/qdash/api/middleware/request_id.py` uses the incoming `X-Request-ID` or generates one,
adds it to logs, and returns it in the response header.

## Adding Logging to New Modules

Use a module logger and structured fields; request correlation is automatic:

```python
import logging

logger = logging.getLogger(__name__)
logger.info("Processing started", extra={"item_id": "123"})
```

Do not log credentials or sensitive request bodies.

## Log File Access

Docker writes `/app/logs/api.log` in the `api-logs` volume. When that path is unavailable,
logging falls back to `${XDG_STATE_HOME:-$HOME/.local/state}/qdash/logs/`, then a temporary
directory if needed. Files rotate at 10 MB with five backups.

## Filtering & Querying

```bash
docker compose logs -f api
docker compose logs --no-log-prefix api | jq 'select(.request_id == "a1b2c3d4")'
```

When changing logging, verify both output handlers and that the same request ID reaches the
response and its log records.

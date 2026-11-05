"""Classify proxied Prefect requests as read-only for the Caddy access gate."""

import re
from urllib.parse import parse_qsl

_UUID = r"[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{12}"
_NAME = r"[A-Za-z0-9._~-]+"

# Excluded on purpose:
# - /block_documents/filter: the body can set include_secrets, which this gate cannot see.
# - /deployments/get_scheduled_flow_runs, /work_queues/{id}/get_runs and
#   /work_pools/{name}/get_scheduled_flow_runs: they update worker polling state.
_POST_READ_PATTERNS = (
    r"/flows/(?:filter|count|paginate)",
    r"/flow_runs/(?:filter|count|paginate|history|lateness)",
    rf"/flow_runs/{_UUID}/input/filter",
    r"/task_runs/(?:filter|count|paginate|history)",
    r"/task_workers/filter",
    r"/deployments/(?:filter|count|paginate)",
    r"/work_queues/filter",
    rf"/work_queues/{_UUID}/concurrency_status",
    r"/work_pools/(?:filter|count)",
    rf"/work_pools/{_NAME}/concurrency_status",
    rf"/work_pools/{_NAME}/queues/filter",
    rf"/work_pools/{_NAME}/workers/filter",
    r"/concurrency_limits/filter",
    r"/v2/concurrency_limits/filter",
    r"/automations/(?:filter|count)",
    r"/block_types/filter",
    r"/block_schemas/filter",
    r"/block_documents/count",
    r"/variables/(?:filter|count)",
    r"/artifacts/(?:filter|count)",
    r"/artifacts/latest/(?:filter|count)",
    r"/logs/filter",
    r"/saved_searches/filter",
    r"/events/filter",
    rf"/events/count-by/{_NAME}",
    r"/ui/flows/(?:count-deployments|next-runs)",
    r"/ui/flow_runs/(?:history|count-task-runs)",
    r"/ui/task_runs/(?:count|dashboard/counts)",
    r"/ui/schemas/validate",
)
_POST_READ_RE = re.compile("/prefect/api(?:" + "|".join(_POST_READ_PATTERNS) + ")")
_WEBSOCKET_READ_PATHS = frozenset({"/prefect/api/events/out", "/prefect/api/logs/out"})


def is_prefect_read_request(method: str, uri: str, upgrade: str = "") -> bool:
    """Return whether a Prefect request is open to any signed-in user.

    This covers reads and allowlisted POST queries. The one write-like exception is
    ``GET /csrf-token``, which stores token rows but is required by the Prefect UI. The raw,
    undecoded path is matched so encoded and dot-segment variants fail closed.

    Parameters
    ----------
    method : str
        HTTP method of the original request.
    uri : str
        Raw request URI including any query string.
    upgrade : str
        Value of the Upgrade header; non-empty for websocket handshakes.

    Returns
    -------
    bool
        True if the request is a read, an allowlisted query, or the CSRF token fetch.

    """
    path, _, query = uri.partition("?")
    if upgrade:
        return method == "GET" and path in _WEBSOCKET_READ_PATHS
    if method in ("GET", "HEAD"):
        return not any(
            key == "include_secrets" for key, _ in parse_qsl(query, keep_blank_values=True)
        )
    if method == "POST":
        return _POST_READ_RE.fullmatch(path) is not None
    return False

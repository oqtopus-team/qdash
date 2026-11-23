# The metric runner: validates and evaluates the API's metric scripts, and
# nothing else. server.ts (PID 1) runs each job as a per-slot uid in a fresh
# job directory and relays its data requests to the API over a Unix socket.
# The container holds no QDash credentials (no env_file) and has no network
# (Compose sets network_mode: none); scripts read data only through the API's
# broker. It shares nothing with the Agent workspace (agent-exec).
#
# Build context: repository root (see compose.yaml).

FROM python:3.11-slim-bookworm
COPY agent-runtime/metric-runner/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && rm /tmp/requirements.txt
# bun runs the supervisor; it needs no node_modules (runner.ts and protocol.ts
# import only node: modules). setpriv comes with util-linux in the base image.
COPY --from=oven/bun:1.4.0 /usr/local/bin/bun /usr/local/bin/bun
COPY agent-runtime/metric-runner/*.ts /app/metric-runner/
# The metric worker and its SDK only: no broker, executor or templates, which
# belong to the API. qdash/ is a namespace package in the repository; the
# empty __init__.py files make the copy a plain package tree.
COPY src/qdash/api/metric_runtime/__init__.py \
     src/qdash/api/metric_runtime/sdk.py \
     src/qdash/api/metric_runtime/policy.py \
     src/qdash/api/metric_runtime/worker.py \
     /app/metric-runtime/qdash/api/metric_runtime/
RUN touch /app/metric-runtime/qdash/__init__.py /app/metric-runtime/qdash/api/__init__.py \
    && command -v setpriv
ENV PYTHONDONTWRITEBYTECODE=1 \
    BUN_RUNTIME_TRANSPILER_CACHE_PATH=/tmp/bun-cache \
    METRIC_RUNNER_PYTHONPATH=/app/metric-runtime
# Root, so each job can be started as its slot's uid (setpriv).
CMD ["bun", "/app/metric-runner/server.ts"]

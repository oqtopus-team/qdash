# syntax=docker/dockerfile:1.7

FROM python:3.11-slim-bookworm AS builder

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
COPY pyproject.toml uv.lock ./
COPY src/qdash/api/pyproject.toml ./src/qdash/api/pyproject.toml
COPY src/qdash/client/pyproject.toml ./src/qdash/client/pyproject.toml
COPY src/qdash/workflow/pyproject.toml ./src/qdash/workflow/pyproject.toml

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --package qdash-api --no-dev

FROM python:3.11-slim-bookworm

WORKDIR /app

RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates curl git nodejs npm ripgrep && \
    rm -rf /var/lib/apt/lists/*

ARG CODEX_INSTALL_COMMAND=""
RUN if [ -n "$CODEX_INSTALL_COMMAND" ]; then sh -lc "$CODEX_INSTALL_COMMAND"; fi

COPY --from=builder /app/.venv /app/.venv
COPY src/qdash /app/qdash
COPY config /app/config

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app:/app/qdash \
    ENABLE_LOCAL_CODEX_AGENT=true

WORKDIR /workspace

CMD ["python", "-m", "qdash.agent.worker"]

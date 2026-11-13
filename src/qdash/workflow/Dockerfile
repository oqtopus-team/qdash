# syntax=docker/dockerfile:1.7

FROM python:3.11-slim-bookworm AS builder

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    build-essential \
    pkg-config \
    libhdf5-dev \
    tzdata \
    curl \
    libcairo2-dev \
    cmake \
    wget \
    git \
    libgirepository1.0-dev \
    gobject-introspection \
    gir1.2-gtk-3.0 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

ENV TZ=Asia/Tokyo
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_HTTP_TIMEOUT=300 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

COPY pyproject.toml uv.lock ./
COPY src/qdash/api/pyproject.toml src/qdash/api/pyproject.toml
COPY clients/python/pyproject.toml clients/python/pyproject.toml
COPY clients/python/README.md clients/python/README.md
COPY src/qdash/workflow/pyproject.toml src/qdash/workflow/pyproject.toml
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --package qdash-workflow --no-dev

FROM python:3.11-slim-bookworm AS runtime

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    libhdf5-dev \
    tzdata \
    curl \
    libcairo2 \
    libgirepository-1.0-1 \
    gir1.2-gtk-3.0 \
    git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

ENV TZ=Asia/Tokyo
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

COPY --from=builder /app/.venv /app/.venv

ENV VIRTUAL_ENV=/app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# -----------------------------------------------------------------------------
# Optional Qibocal runner (build target `qibocal`, used by compose.qibocal.yaml)
# -----------------------------------------------------------------------------
# Qibocal and Qibolab pin `cma<4` while qubex needs `cma>=4`, so the runner gets its own
# environment from its own lock under /app/src/qdash/workflow/qibocal_runner. QDash starts it as a
# subprocess and never imports it. The default target below does not build these stages.
FROM python:3.11-slim-bookworm AS qibocal-runner-builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_HTTP_TIMEOUT=300 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app/src/qdash/workflow/qibocal_runner
COPY src/qdash/workflow/qibocal_runner/pyproject.toml src/qdash/workflow/qibocal_runner/uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --python /usr/local/bin/python3.11
COPY src/qdash/workflow/qibocal_runner/run_protocol.py ./
# The platform files the runner reads are copied from upstream Qibocal under Apache 2.0.
COPY config/domain/qibocal/LICENSE config/domain/qibocal/UPSTREAM.md ./licenses/qibocal-platform/

FROM runtime AS qibocal

# The installed distributions keep their LICENSE and NOTICE files in their .dist-info
# directories inside .venv; copy the environment whole so those files stay in the image.
COPY --from=qibocal-runner-builder /app/src/qdash/workflow/qibocal_runner /app/src/qdash/workflow/qibocal_runner
COPY src/qdash/common/qibocal_platform.py /app/src/qdash/common/qibocal_platform.py

# Default target: the worker without the Qibocal runner.
FROM runtime AS default

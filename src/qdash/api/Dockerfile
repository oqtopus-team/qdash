# syntax=docker/dockerfile:1.7

FROM python:3.11-slim-bookworm AS builder

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    build-essential \
    pkg-config \
    libhdf5-dev \
    curl \
    wget \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

COPY pyproject.toml uv.lock ./
COPY src/qdash/api/pyproject.toml src/qdash/api/pyproject.toml
COPY src/qdash/workflow/pyproject.toml src/qdash/workflow/pyproject.toml
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --package qdash-api --no-dev

FROM python:3.11-slim-bookworm

WORKDIR /app

# Install git for GitPython operations
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app/.venv /app/.venv

ENV VIRTUAL_ENV=/app/.venv
ENV PATH="/app/.venv/bin:$PATH"

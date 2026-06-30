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
COPY src/qdash/client/pyproject.toml src/qdash/client/pyproject.toml
COPY src/qdash/client/README.md src/qdash/client/README.md
COPY src/qdash/workflow/pyproject.toml src/qdash/workflow/pyproject.toml
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --package qdash-workflow --no-dev

FROM python:3.11-slim-bookworm

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

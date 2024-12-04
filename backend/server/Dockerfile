FROM python:3.10.14-slim-bookworm AS builder

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

COPY ./backend/server/requirements.txt ./

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
RUN uv pip install --system --no-cache-dir -r requirements.txt

FROM python:3.10.14-slim-bookworm

WORKDIR /app

COPY --from=builder /app /app
COPY --from=builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

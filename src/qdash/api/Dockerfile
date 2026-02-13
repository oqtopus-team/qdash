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

COPY ./src/qdash/api/requirements.txt ./

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
RUN uv pip install --system --no-cache-dir -r requirements.txt
RUN uv pip install --upgrade --system --no-cache-dir pydantic-settings==2.3.4
RUN uv pip install --upgrade --system --no-cache-dir prefect-client==2.19.9
RUN uv pip install --system --no-cache-dir "openai>=1.75.0"

FROM python:3.10.14-slim-bookworm

WORKDIR /app

# Install git for GitPython operations
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /app /app
COPY --from=builder /usr/local/lib/python3.10/site-packages /usr/local/lib/python3.10/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

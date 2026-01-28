FROM prefecthq/prefect:2.20.18-python3.11 AS builder

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
    libgirepository1.0-dev \
    gobject-introspection \
    gir1.2-gtk-3.0 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

ENV TZ=Asia/Tokyo
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

COPY ./src/qdash/workflow/requirements.txt ./

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
ENV UV_HTTP_TIMEOUT=300
RUN uv pip install --system --no-cache-dir -r requirements.txt
## for update pydantic ignoring quel-ic-config dependency
RUN uv pip install --upgrade --system --no-cache-dir pydantic
RUN uv pip install --upgrade --system --no-cache-dir pydantic-settings==2.3.4
## for multiprocess parallel execution (install after pydantic upgrade)
RUN uv pip install --system --no-cache-dir prefect-dask==0.2.10

FROM prefecthq/prefect:2.20.18-python3.11

WORKDIR /app

ENV TZ=Asia/Tokyo
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
ENV PYTHONPATH=/usr/local/lib/python3.11/site-packages

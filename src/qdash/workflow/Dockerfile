FROM prefecthq/prefect:2.20-python3.11 AS builder

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
    build-essential \
    pkg-config \
    libhdf5-dev \
    tzdata \
    curl \
    wget \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

ENV TZ=Asia/Tokyo
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

COPY ./src/qdash/workflow/requirements.txt ./

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
RUN uv pip install --system --no-cache-dir -r requirements.txt
## for update pydantic ignoring quel-ic-config dependency
RUN uv pip install --upgrade --system --no-cache-dir pydantic

FROM prefecthq/prefect:2.20-python3.11


WORKDIR /app

ENV TZ=Asia/Tokyo
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
ENV PYTHONPATH=/usr/local/lib/python3.11/site-packages


# RUN prefect config set PREFECT_EXPERIMENTAL_ENABLE_ENHANCED_CANCELLATION=True

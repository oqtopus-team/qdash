FROM python:3.11-slim

WORKDIR /app

COPY ./src/qdash/slack_agent/requirements.txt ./

# 依存関係ファイルをコピー
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
RUN uv pip install --system --no-cache-dir -r requirements.txt

WORKDIR /app

ENV TZ=Asia/Tokyo
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

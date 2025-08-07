FROM python:3.11-slim

WORKDIR /app

# Copy the entire project to support editable install (-e .)
COPY . .

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Install dependencies from requirements.txt
RUN uv pip install --system --no-cache-dir -r src/qdash/slack_agent/requirements.txt

ENV TZ=Asia/Tokyo
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

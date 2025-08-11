# Dockerfile for Strands-based Slack Agent
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY . .

# Install uv and basic dependencies
RUN pip install uv

# Install only agent-specific dependencies to avoid conflicts
RUN pip install \
    "aiohttp>=3.8.0,<4.0.0" \
    "openai>=1.98.0" \
    "slack-bolt>=1.18.0" \
    pydantic-settings \
    "bunnet>=1.3.0" \
    "pymongo>=4.8.0" \
    pendulum \
    "numpy>=1.26.0" \
    "prefect==2.20.0"

# Install Strands Agents SDK directly from GitHub
RUN pip install git+https://github.com/strands-agents/sdk-python.git

# Set Python path to include src
ENV PYTHONPATH=/app/src:$PYTHONPATH

# Create logs directory
RUN mkdir -p /app/src/qdash/slack_agent/log

# Set default command to run agent
CMD ["python", "src/qdash/slack_agent/main.py"]

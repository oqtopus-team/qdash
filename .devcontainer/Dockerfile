# ========================================
# Stage 1: Base image and system packages
# Change frequency: Low - Most likely to be cached
# ========================================
FROM python:3.10.14-slim-bookworm as base

# Install system packages by category
# Docker CLI + compose plugin (Docker official installation)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    gnupg \
 && install -m 0755 -d /etc/apt/keyrings \
 && curl -fsSL https://download.docker.com/linux/debian/gpg \
      | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
 && chmod a+r /etc/apt/keyrings/docker.gpg \
 && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
      https://download.docker.com/linux/debian bookworm stable" \
      > /etc/apt/sources.list.d/docker.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends \
      docker-ce-cli \
      docker-compose-plugin \
 && rm -rf /var/lib/apt/lists/*

# 1. Essential build tools (Change frequency: Lowest)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    make \
    cmake \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# 2. Python-related dependencies (Change frequency: Low)
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-dev \
    libpq-dev \
    libhdf5-dev \
    libcairo2-dev \
    libgirepository1.0-dev \
    gir1.2-gtk-3.0 \
    && rm -rf /var/lib/apt/lists/*

# 3. Development tools (Change frequency: Medium)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    wget \
    jq \
    unzip \
    sudo \
    fzf \
    && rm -rf /var/lib/apt/lists/*

# 4. Editors and shells (Change frequency: Medium)
RUN apt-get update && apt-get install -y --no-install-recommends \
    vim \
    zsh \
    && rm -rf /var/lib/apt/lists/*

# ========================================
# Stage 2: Python environment setup
# ========================================
FROM base as python-env

# Install pip and uv
RUN curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py && \
    python get-pip.py && \
    rm get-pip.py

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /workspace/qdash

# Install Python dependencies (copy only requirements.txt)
COPY ./.devcontainer/requirements.txt ./requirements.txt
RUN uv pip install --system --no-cache -r requirements.txt && \
    uv pip install --system --no-cache prefect==2.20.0

# ========================================
# Stage 3: Node.js environment
# ========================================
FROM python-env as node-env

ARG NODE_VERSION=20
RUN curl -fsSL https://deb.nodesource.com/setup_${NODE_VERSION}.x | bash - && \
    apt-get install -y nodejs && \
    apt-get clean && rm -rf /var/lib/apt/lists/* && \
    node -v && npm -v

# Install bun
RUN curl -fsSL https://bun.sh/install | bash
ENV PATH="/root/.bun/bin:${PATH}"

# ========================================
# Stage 4: Pre-install frontend dependencies
# Copy only package.json and bun.lock first to install dependencies
# ========================================
FROM node-env as frontend-deps

WORKDIR /workspace/qdash/ui

# Copy only package.json and bun.lock (cache optimization)
COPY ./ui/package.json ./package.json

# Install dependencies
RUN bun install
# ========================================
# Stage 5: Final image
# ========================================
FROM node-env as final

# Install Claude Code
ARG CLAUDE_CODE_VERSION=latest
RUN npm install -g @anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}


# Configure Zsh (execute last)
ENV SHELL=/bin/zsh

# Install fzf shell integration files
RUN mkdir -p /usr/share/doc/fzf/examples && \
    curl -fsSL https://raw.githubusercontent.com/junegunn/fzf/master/shell/key-bindings.zsh -o /usr/share/doc/fzf/examples/key-bindings.zsh && \
    curl -fsSL https://raw.githubusercontent.com/junegunn/fzf/master/shell/completion.zsh -o /usr/share/doc/fzf/examples/completion.zsh && \
    curl -fsSL https://raw.githubusercontent.com/junegunn/fzf/master/shell/key-bindings.bash -o /usr/share/doc/fzf/examples/key-bindings.bash && \
    curl -fsSL https://raw.githubusercontent.com/junegunn/fzf/master/shell/completion.bash -o /usr/share/doc/fzf/examples/completion.bash

ARG ZSH_IN_DOCKER_VERSION=1.2.0
RUN sh -c "$(wget -O- https://github.com/deluan/zsh-in-docker/releases/download/v${ZSH_IN_DOCKER_VERSION}/zsh-in-docker.sh)" -- \
    -p git \
    -p fzf \
    -a "export FZF_BASE=/usr/bin" \
    -a "export PROMPT_COMMAND='history -a' && export HISTFILE=/commandhistory/.bash_history" \
    -a "umask 022" \
    -x

# Setup node_modules cache directory
# This will be used by postCreateCommand
RUN mkdir -p /workspace/qdash/ui && \
    touch /workspace/qdash/ui/.bunfig.toml

# Copy frontend dependencies to correct location
# This pre-populates node_modules before volume mount
COPY --from=frontend-deps /workspace/qdash/ui/node_modules /workspace/qdash/ui/node_modules

WORKDIR /workspace/qdash

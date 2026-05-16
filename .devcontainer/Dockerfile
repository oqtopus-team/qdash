# ========================================
# Stage 1: Base image and system packages
# Change frequency: Low - Most likely to be cached
# ========================================
ARG TRUFFLEHOG_VERSION=3.95.3
ARG GITLEAKS_VERSION=v8.30.1
ARG LEFTHOOK_VERSION=2.1.6
ARG UV_VERSION=0.11.11
ARG BUN_VERSION=1.3.14
ARG CODEX_VERSION=0.130.0

FROM ghcr.io/gitleaks/gitleaks:${GITLEAKS_VERSION} AS gitleaks-bin
FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv-bin
FROM oven/bun:${BUN_VERSION} AS bun-bin
FROM python:3.11.14-slim-bookworm AS base

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
    bash \
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
    && rm -rf /var/lib/apt/lists/*

ARG USERNAME=vscode
ARG USER_UID=1000
ARG USER_GID=${USER_UID}
RUN groupadd --gid ${USER_GID} ${USERNAME} \
    && useradd --uid ${USER_UID} --gid ${USER_GID} -m -s /bin/bash ${USERNAME} \
    && echo "${USERNAME} ALL=(root) NOPASSWD:ALL" > /etc/sudoers.d/${USERNAME} \
    && chmod 0440 /etc/sudoers.d/${USERNAME}

# 3.1 GitHub CLI
RUN curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
      | dd of=/usr/share/keyrings/githubcli-archive-keyring.gpg \
    && chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
      > /etc/apt/sources.list.d/github-cli.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends gh \
    && rm -rf /var/lib/apt/lists/*

ARG TRUFFLEHOG_VERSION
ARG GITLEAKS_VERSION
ARG LEFTHOOK_VERSION

# 3.2 Secret scanning tools (gitleaks + trufflehog) and git hooks manager (lefthook)
RUN curl -sSfL https://raw.githubusercontent.com/trufflesecurity/trufflehog/main/scripts/install.sh \
      | sh -s -- -b /usr/local/bin "v${TRUFFLEHOG_VERSION}"

RUN curl -1sLf 'https://dl.cloudsmith.io/public/evilmartians/lefthook/setup.deb.sh' | bash \
    && apt-get install -y --no-install-recommends "lefthook=${LEFTHOOK_VERSION}" \
    && rm -rf /var/lib/apt/lists/*

COPY --from=gitleaks-bin /usr/bin/gitleaks /usr/local/bin/gitleaks

# 4. Editors and shells (Change frequency: Medium)
RUN apt-get update && apt-get install -y --no-install-recommends \
    vim \
    zsh \
    && rm -rf /var/lib/apt/lists/*

# ========================================
# Stage 2: Python environment setup
# ========================================
FROM base AS toolchain
COPY --from=uv-bin /uv /uvx /bin/

WORKDIR /workspace/qdash
# ========================================
# Stage 3: Node.js environment
# ========================================
FROM toolchain AS node-env

ARG NODE_VERSION=20
RUN curl -fsSL https://deb.nodesource.com/setup_${NODE_VERSION}.x | bash - && \
    apt-get install -y nodejs && \
    apt-get clean && rm -rf /var/lib/apt/lists/* && \
    node -v && npm -v

# Install bun in a shared location so either root or a dev user can run it.
ENV BUN_INSTALL=/usr/local/bun
COPY --from=bun-bin /usr/local/bin/bun /usr/local/bin/bun
RUN mkdir -p "${BUN_INSTALL}/bin" \
    && ln -sf /usr/local/bin/bun "${BUN_INSTALL}/bin/bun" \
    && ln -sf /usr/local/bin/bun "${BUN_INSTALL}/bin/bunx" \
    && ln -sf "${BUN_INSTALL}/bin/bunx" /usr/local/bin/bunx
ENV PATH="${BUN_INSTALL}/bin:${PATH}"

# ========================================
# Stage 4: Final image
# ========================================
FROM node-env AS final
ARG CODEX_VERSION

# Set default file permissions (644 for files, 755 for directories)
# This ensures files created in devcontainer are readable in Docker builds
RUN echo "umask 022" >> /etc/profile && \
    echo "umask 022" >> /etc/bash.bashrc

ENV HOME=/root
ENV PATH="/root/.local/bin:${PATH}"

# Install OpenAI Codex CLI
RUN npm install -g "@openai/codex@${CODEX_VERSION}" && \
    codex --version

# Configure Zsh.
ENV SHELL=/bin/zsh

# Setup workspace and cache directories.
RUN mkdir -p \
        /workspace/qdash/ui \
        /commandhistory \
        /root/.cache/pip \
        /root/.cache/uv \
        /root/.claude \
        /root/.codex \
        /root/.vscode-server/extensions \
    && touch /workspace/qdash/ui/.bunfig.toml \
    && touch /root/.bashrc /root/.zshrc \
    && echo 'export PATH="$HOME/.local/bin:$PATH"' >> /root/.bashrc \
    && echo 'export PATH="$HOME/.local/bin:$PATH"' >> /root/.zshrc \
    && echo 'export HISTFILE=/commandhistory/.zsh_history' >> /root/.zshrc \
    && echo 'setopt APPEND_HISTORY' >> /root/.zshrc \
    && echo 'setopt HIST_IGNORE_DUPS' >> /root/.zshrc \
    && chsh -s /bin/zsh root

COPY ./.devcontainer/update-docker-socket-group.sh /usr/local/bin/update-docker-socket-group
COPY ./.devcontainer/start-container.sh /usr/local/bin/start-container
COPY ./.devcontainer/post-create.sh /usr/local/bin/qdash-post-create
COPY ./.devcontainer/post-start.sh /usr/local/bin/qdash-post-start
RUN chmod 0755 \
        /usr/local/bin/update-docker-socket-group \
        /usr/local/bin/start-container \
        /usr/local/bin/qdash-post-create \
        /usr/local/bin/qdash-post-start

WORKDIR /workspace/qdash

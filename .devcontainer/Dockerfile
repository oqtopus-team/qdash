# ========================================
# Stage 1: Base image and system packages
# Change frequency: Low - Most likely to be cached
# ========================================
ARG TRUFFLEHOG_VERSION=3.95.3
ARG BETTERLEAKS_VERSION=v1.3.1
ARG LEFTHOOK_VERSION=2.1.6
ARG UV_VERSION=0.11.11
ARG BUN_VERSION=1.4.0
ARG CODEX_VERSION=0.130.0

FROM ghcr.io/betterleaks/betterleaks:${BETTERLEAKS_VERSION} AS betterleaks-bin
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
    bubblewrap \
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
ARG BETTERLEAKS_VERSION
ARG LEFTHOOK_VERSION

# 3.2 Secret scanning tools (betterleaks + trufflehog) and git hooks manager (lefthook)
RUN curl -sSfL https://raw.githubusercontent.com/trufflesecurity/trufflehog/main/scripts/install.sh \
      | sh -s -- -b /usr/local/bin "v${TRUFFLEHOG_VERSION}"

RUN curl -1sLf 'https://dl.cloudsmith.io/public/evilmartians/lefthook/setup.deb.sh' | bash \
    && apt-get install -y --no-install-recommends "lefthook=${LEFTHOOK_VERSION}" \
    && rm -rf /var/lib/apt/lists/*

COPY --from=betterleaks-bin /usr/bin/betterleaks /usr/local/bin/betterleaks

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

ARG NODE_VERSION=24
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

ENV HOME=/home/vscode
ENV NPM_CONFIG_PREFIX=/opt/codex
ENV PATH="/opt/codex/bin:/home/vscode/.local/bin:${PATH}"

# Install OpenAI Codex CLI into a writable prefix that is not hidden by the
# persisted /home/vscode/.local volume.
RUN mkdir -p /opt/codex /home/vscode/.local /home/vscode/.npm \
    && chown -R vscode:vscode /opt/codex /home/vscode/.local /home/vscode/.npm
USER vscode
RUN npm install -g "@openai/codex@${CODEX_VERSION}" && \
    codex --version
USER root

# Configure Zsh.
ENV SHELL=/bin/zsh

# Install zsh prompt/theme tooling for an improved interactive shell.
RUN git clone --depth=1 https://github.com/romkatv/powerlevel10k.git /opt/powerlevel10k \
    && git clone --depth=1 https://github.com/zsh-users/zsh-autosuggestions.git /opt/zsh-autosuggestions \
    && git clone --depth=1 https://github.com/zsh-users/zsh-syntax-highlighting.git /opt/zsh-syntax-highlighting

COPY ./zshrc.qdash /opt/qdash-devcontainer/zshrc.qdash
COPY ./p10k.zsh /opt/qdash-devcontainer/p10k.zsh

# Setup workspace and cache directories.
RUN mkdir -p \
        /workspace/qdash/ui \
        /commandhistory \
        /home/vscode/.cache/pip \
        /home/vscode/.cache/uv \
        /home/vscode/.claude \
        /home/vscode/.codex \
        /home/vscode/.vscode-server/extensions \
    && touch /workspace/qdash/ui/.bunfig.toml \
    && touch /home/vscode/.bashrc /home/vscode/.zshrc \
    && echo 'export PATH="$HOME/.local/bin:$PATH"' >> /home/vscode/.bashrc \
    && echo 'export PATH="$HOME/.local/bin:$PATH"' >> /home/vscode/.zshrc \
    && printf '\n# >>> qdash managed zsh >>>\nif [ -f /workspace/qdash/.devcontainer/zshrc.qdash ]; then\n  source /workspace/qdash/.devcontainer/zshrc.qdash\nelif [ -f /opt/qdash-devcontainer/zshrc.qdash ]; then\n  source /opt/qdash-devcontainer/zshrc.qdash\nfi\n# <<< qdash managed zsh <<<\n' >> /home/vscode/.zshrc \
    && chown -R vscode:vscode \
        /commandhistory \
        /home/vscode/.cache \
        /home/vscode/.claude \
        /home/vscode/.codex \
        /home/vscode/.local \
        /home/vscode/.npm \
        /home/vscode/.vscode-server \
        /home/vscode/.bashrc \
        /home/vscode/.zshrc \
        /opt/codex \
        /opt/qdash-devcontainer \
    && chsh -s /bin/zsh vscode

COPY ./update-docker-socket-group.sh /usr/local/bin/update-docker-socket-group
COPY ./start-container.sh /usr/local/bin/start-container
COPY ./post-create.sh /usr/local/bin/qdash-post-create
COPY ./post-start.sh /usr/local/bin/qdash-post-start
RUN chmod 0755 \
        /usr/local/bin/update-docker-socket-group \
        /usr/local/bin/start-container \
        /usr/local/bin/qdash-post-create \
        /usr/local/bin/qdash-post-start

WORKDIR /workspace/qdash

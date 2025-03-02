FROM python:3.10.14-slim-bookworm

RUN apt-get update && apt-get install -y \
    sudo \
    vim \
    git \
    curl \
    wget \
    gcc \
    g++ \
    libpq-dev \
    make \
    cmake \
    libcairo2-dev \
    libgirepository1.0-dev \
    python3-dev \
    gir1.2-gtk-3.0\
    pkg-config \
    libhdf5-dev \
    jq  \
    && rm -rf /var/lib/apt/lists/*


RUN curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py && python get-pip.py && rm get-pip.py

WORKDIR /workspace/qdash

COPY ./.devcontainer/requirements.txt .
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
RUN uv pip install --system --no-cache -r requirements.txt
RUN uv pip install --system --no-cache prefect==2.20.0

RUN curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
RUN apt-get install -y nodejs

# COPY ./client/package*.json ./client/pnpm-lock.yaml ./
# RUN npm install -g pnpm
# RUN pnpm install
COPY ./ui/package*.json ./
# pnpm をインストール
#RUN npm install -g pnpm
RUN npm install
RUN npm install -g @go-task/cli

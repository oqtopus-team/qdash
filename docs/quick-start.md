---
layout: doc
---

# Quick Start

## Install

```bash
git clone https://github.com/oqtopus-team/qdash.git
```

## Initial Setup

Run the following commands to create the necessary directories and environment files.

```bash
chmod +x scripts/create_directory.sh scripts/create_env.sh scripts/init.sh
scripts/init.sh
```

## Start the Development Environment

```bash
docker compose up -d
```

## Initialize the Database

```bash
 docker compose -f compose.dev.yaml up -d
```

```bash
docker exec -it qdash-devcontainer /bin/bash -c "python init/setup.py init-all"
```

You can now access the application at <a href="http://localhost:5714"> here </a>.

## Delete the Database

```bash
docker exec -it qdash-devcontainer /bin/bash -c "python init/setup.py teardown-all"
```

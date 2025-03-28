#!/bin/bash

env_content='ENV="oqtopus"
# Ports
MONGO_PORT=27017
MONGO_EXPRESS_PORT=8081
POSTGRES_PORT=5432
PREFECT_PORT=4200
API_PORT=5715
UI_PORT=5714


# URLs
CLIENT_URL=http://localhost:${UI_PORT:-5714}
NEXT_PUBLIC_API_URL=http://localhost:${API_PORT:-5715}
PREFECT_API_URL=http://prefect-server:${PREFECT_PORT:-4200}/api

# MongoDB
MONGO_INITDB_ROOT_USERNAME=root
MONGO_INITDB_ROOT_PASSWORD=example

# PostgreSQL
POSTGRES_USER=postgres
POSTGRES_PASSWORD=prefect
POSTGRES_DB=prefect

# Data paths
POSTGRES_DATA_PATH="./postgres_data"
MONGO_DATA_PATH="./mongo_data/data/db"
CALIB_DATA_PATH="./calib_data"
QPU_DATA_PATH="./qpu_data"

# Optional settings
SLACK_BOT_TOKEN=""

CONFIG_PATH="./config"
'

echo "$env_content" > .env

echo "Created .env file"

#!/usr/bin/env bash
set -euo pipefail

ENV_FILE="${ENV_FILE:-.env}"

if [ ! -f "$ENV_FILE" ]; then
  echo "Missing .env. Create it with: cp .env.example .env" >&2
  exit 1
fi

env_value() {
  local key="$1"
  awk -v key="$key" '
    $0 ~ "^[[:space:]]*(export[[:space:]]+)?" key "[[:space:]]*=" {
      line = $0
      sub(/^[[:space:]]*export[[:space:]]+/, "", line)
      sub("^[[:space:]]*" key "[[:space:]]*=", "", line)
      sub(/[[:space:]]+#.*/, "", line)
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", line)
      gsub(/^"|"$/, "", line)
      gsub(/^'\''|'\''$/, "", line)
      value = line
    }
    END { print value }
  ' "$ENV_FILE"
}

shell_quote() {
  printf "'%s'" "$(printf "%s" "$1" | sed "s/'/'\\\\''/g")"
}

emit_export() {
  local key="$1"
  local value="$2"
  printf "export %s=%s\n" "$key" "$(shell_quote "$value")"
}

env_name="${ENV:-$(env_value ENV)}"
env_name="${env_name:-qdash}"

qdash_instance="${QDASH_INSTANCE:-$(env_value QDASH_INSTANCE)}"
qdash_instance="${qdash_instance:-${env_name}-qdash}"

compose_project_name="${COMPOSE_PROJECT_NAME:-$(env_value COMPOSE_PROJECT_NAME)}"
compose_project_name="${compose_project_name:-$qdash_instance}"

local_domain="${QDASH_LOCAL_DOMAIN:-$(env_value QDASH_LOCAL_DOMAIN)}"
local_domain="${local_domain:-qdash.test}"

local_host="${QDASH_LOCAL_HOST:-$(env_value QDASH_LOCAL_HOST)}"
local_host="${local_host:-${env_name}.${local_domain}}"

proxy_port="${PROXY_PORT:-$(env_value PROXY_PORT)}"
proxy_port="${proxy_port:-18080}"

ui_port="${UI_PORT:-$(env_value UI_PORT)}"
ui_port="${ui_port:-5714}"

api_port="${API_PORT:-$(env_value API_PORT)}"
api_port="${api_port:-5715}"

qdash_host="${QDASH_HOST:-$(env_value QDASH_HOST)}"
client_url="${CLIENT_URL:-$(env_value CLIENT_URL)}"
case "$client_url" in
  ""|*'$'*)
    client_url="https://${qdash_host}"
    ;;
esac

next_public_api_url="${NEXT_PUBLIC_API_URL:-$(env_value NEXT_PUBLIC_API_URL)}"
next_public_api_url="${next_public_api_url:-/api}"

prefect_url="${NEXT_PUBLIC_PREFECT_URL:-$(env_value NEXT_PUBLIC_PREFECT_URL)}"
case "$prefect_url" in
  ""|*'$'*)
    prefect_url="http://prefect.${local_host}:${proxy_port}"
    ;;
esac

emit_export ENV "$env_name"
emit_export QDASH_INSTANCE "$qdash_instance"
emit_export COMPOSE_PROJECT_NAME "$compose_project_name"
emit_export QDASH_LOCAL_DOMAIN "$local_domain"
emit_export QDASH_LOCAL_HOST "$local_host"
emit_export QDASH_API_HOST "api.${local_host}"
emit_export QDASH_PREFECT_HOST "prefect.${local_host}"
emit_export QDASH_MONGO_HOST "mongo.${local_host}"
emit_export PROXY_PORT "$proxy_port"
emit_export CLIENT_URL "$client_url"
emit_export NEXT_PUBLIC_API_URL "$next_public_api_url"
emit_export NEXT_PUBLIC_PREFECT_URL "$prefect_url"
emit_export QDASH_UI_UPSTREAM "ui:${ui_port}"
emit_export QDASH_API_UPSTREAM "api:${api_port}"

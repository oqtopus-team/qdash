#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="${ROOT_DIR}/.env"

PORT_KEYS=(
  PROXY_PORT
  MONGO_PORT
  MONGO_EXPRESS_PORT
  POSTGRES_PORT
  PREFECT_PORT
  API_PORT
  UI_PORT
  DEPLOYMENT_SERVICE_PORT
)

if [ ! -f "$ENV_FILE" ]; then
  echo "Missing .env. Create it with: cp .env.example .env" >&2
  exit 1
fi

sanitize() {
  printf "%s" "$1" \
    | tr "[:upper:]_" "[:lower:]-" \
    | sed -E "s/[^a-z0-9-]+/-/g; s/^-+//; s/-+$//; s/-+/-/g"
}

instance_name() {
  local value
  value="$(sanitize "$1")"
  if [ -z "$value" ]; then
    value="dev-qdash"
  fi
  case "$value" in
    *-qdash) printf "%s" "$value" ;;
    *) printf "%s-qdash" "$value" ;;
  esac
}

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
      print line
      exit
    }
  ' "$ENV_FILE"
}

has_env_key() {
  local key="$1"
  awk -v key="$key" '
    $0 ~ "^[[:space:]]*(export[[:space:]]+)?" key "[[:space:]]*=" { found = 1 }
    END { exit found ? 0 : 1 }
  ' "$ENV_FILE"
}

port_is_used() {
  local port="$1"
  lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1
}

contains_port() {
  local port="$1"
  local existing
  for existing in "${ASSIGNED_PORTS[@]}"; do
    if [ "$existing" = "$port" ]; then
      return 0
    fi
  done
  return 1
}

find_free_port() {
  local offset="$1"
  local candidate
  local step=0
  while [ "$step" -lt 30000 ]; do
    candidate=$((20000 + ((PORT_BASE + offset + step) % 30000)))
    if ! contains_port "$candidate" && ! port_is_used "$candidate"; then
      ASSIGNED_PORTS+=("$candidate")
      printf "%s" "$candidate"
      return 0
    fi
    step=$((step + 1))
  done
  echo "Could not find a free TCP port" >&2
  exit 1
}

env_name="$(instance_name "${ENV:-$(env_value ENV)}")"
raw_instance="${QDASH_INSTANCE:-$(env_value QDASH_INSTANCE)}"
if [ -n "$raw_instance" ]; then
  instance="$(instance_name "$raw_instance")"
else
  instance="$env_name"
fi

proxy_name="$instance"
host="${proxy_name}.localhost"
force=0
if [ "${1:-}" = "--force" ]; then
  force=1
fi

keep_ports=1
if [ "$force" -eq 1 ] || [ "$(env_value COMPOSE_PROJECT_NAME)" != "$proxy_name" ]; then
  keep_ports=0
fi

for key in "${PORT_KEYS[@]}"; do
  if [ -z "$(env_value "$key")" ]; then
    keep_ports=0
  fi
done

ASSIGNED_PORTS=()
hash_input="$proxy_name"
PORT_BASE="$(printf "%s" "$hash_input" | cksum | awk '{ print $1 % 30000 }')"

declare -A updates
updates[ENV]="$env_name"
updates[COMPOSE_PROJECT_NAME]="$proxy_name"
updates[QDASH_INSTANCE]="$instance"
updates[QDASH_HOST]="$host"
updates[QDASH_API_HOST]="api.${host}"
updates[QDASH_PREFECT_HOST]="prefect.${host}"
updates[QDASH_MONGO_HOST]="mongo.${host}"

for index in "${!PORT_KEYS[@]}"; do
  key="${PORT_KEYS[$index]}"
  if [ "$keep_ports" -eq 1 ]; then
    value="$(env_value "$key")"
    ASSIGNED_PORTS+=("$value")
    updates[$key]="$value"
  else
    updates[$key]="$(find_free_port "$index")"
  fi
done

updates[CLIENT_URL]='http://${ENV}.localhost:${PROXY_PORT}'
updates[NEXT_PUBLIC_API_URL]="/api"
updates[NEXT_PUBLIC_PREFECT_URL]='http://prefect.${ENV}.localhost:${PROXY_PORT}'
updates[QDASH_UI_UPSTREAM]="ui:${updates[UI_PORT]}"
updates[QDASH_API_UPSTREAM]="api:${updates[API_PORT]}"
updates[PREFECT_API_URL]='http://localhost:${PREFECT_PORT}/api'
updates[INTERNAL_API_URL]='http://api:${API_PORT}'

tmp_file="$(mktemp)"
missing_port_keys=()
for key in "${PORT_KEYS[@]}"; do
  if ! has_env_key "$key"; then
    missing_port_keys+=("$key")
  fi
done

inserted_ports=0
seen_file="$(mktemp)"
while IFS= read -r line || [ -n "$line" ]; do
  matched_key=""
  for key in "${!updates[@]}"; do
    if [[ "$line" =~ ^[[:space:]]*(export[[:space:]]+)?${key}[[:space:]]*= ]]; then
      prefix="${line%%=*}"
      printf "%s=%s\n" "$prefix" "${updates[$key]}" >> "$tmp_file"
      printf "%s\n" "$key" >> "$seen_file"
      matched_key="$key"
      break
    fi
  done
  if [ -z "$matched_key" ]; then
    printf "%s\n" "$line" >> "$tmp_file"
  fi
  if [ "$line" = "# Ports" ] && [ "${#missing_port_keys[@]}" -gt 0 ]; then
    for key in "${missing_port_keys[@]}"; do
      printf "%s=%s\n" "$key" "${updates[$key]}" >> "$tmp_file"
      printf "%s\n" "$key" >> "$seen_file"
    done
    inserted_ports=1
  fi
done < "$ENV_FILE"

if [ "$inserted_ports" -eq 0 ] && [ "${#missing_port_keys[@]}" -gt 0 ]; then
  printf "\n" >> "$tmp_file"
  for key in "${missing_port_keys[@]}"; do
    printf "%s=%s\n" "$key" "${updates[$key]}" >> "$tmp_file"
    printf "%s\n" "$key" >> "$seen_file"
  done
fi

for key in "${!updates[@]}"; do
  if ! grep -qx "$key" "$seen_file"; then
    printf "%s=%s\n" "$key" "${updates[$key]}" >> "$tmp_file"
  fi
done

mv "$tmp_file" "$ENV_FILE"
rm -f "$seen_file"

if [ "$keep_ports" -eq 1 ]; then
  echo "Verified .env for $instance"
else
  echo "Updated .env for $instance"
fi
echo "Compose project: $proxy_name"
echo "Proxy: http://${host}:${updates[PROXY_PORT]}"
echo "API: http://api.${host}:${updates[PROXY_PORT]}"
echo "Prefect: http://prefect.${host}:${updates[PROXY_PORT]}"

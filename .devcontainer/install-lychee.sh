#!/usr/bin/env bash
set -euo pipefail

LYCHEE_VERSION="${LYCHEE_VERSION:-0.24.2}"
LYCHEE_INSTALL_DIR="${LYCHEE_INSTALL_DIR:-${HOME}/.local/bin}"

if command -v lychee >/dev/null 2>&1; then
  installed_version="$(lychee --version 2>/dev/null | awk '{print $2}' || true)"
  if [[ "${installed_version}" == "${LYCHEE_VERSION}" ]]; then
    echo "Lychee ${LYCHEE_VERSION} is already installed."
    exit 0
  fi
fi

case "$(uname -s)-$(uname -m)" in
  Linux-x86_64) target="x86_64-unknown-linux-musl" ;;
  Linux-aarch64 | Linux-arm64) target="aarch64-unknown-linux-musl" ;;
  Darwin-x86_64) target="x86_64-apple-darwin" ;;
  Darwin-arm64 | Darwin-aarch64) target="aarch64-apple-darwin" ;;
  *)
    echo "Unsupported platform for Lychee: $(uname -s) $(uname -m)" >&2
    exit 1
    ;;
esac

archive="lychee-${target}.tar.gz"
release_url="https://github.com/lycheeverse/lychee/releases/download/lychee-v${LYCHEE_VERSION}"
temp_dir="$(mktemp -d)"
trap 'rm -rf "${temp_dir}"' EXIT

curl --fail --location --silent --show-error \
  --output "${temp_dir}/${archive}" "${release_url}/${archive}"
curl --fail --location --silent --show-error \
  --output "${temp_dir}/${archive}.sha256" "${release_url}/${archive}.sha256"

if command -v sha256sum >/dev/null 2>&1; then
  (cd "${temp_dir}" && sha256sum --check "${archive}.sha256")
else
  (cd "${temp_dir}" && shasum --algorithm 256 --check "${archive}.sha256")
fi

tar --extract --gzip --file "${temp_dir}/${archive}" --directory "${temp_dir}"
mkdir -p "${LYCHEE_INSTALL_DIR}"
install -m 0755 "${temp_dir}/lychee-${target}/lychee" "${LYCHEE_INSTALL_DIR}/lychee"
"${LYCHEE_INSTALL_DIR}/lychee" --version

#!/usr/bin/env bash
# The prebuilt images of the QDash Demo (sample data) and their tags.
#
# Usage: images.sh env|matrix|inputs|refs
#
#   env     Print QDASH_DEMO_*_IMAGE="<ref>" lines for .env (demo.sh writes them).
#   matrix  Print the build matrix as JSON for .github/workflows/demo-images.yml.
#   inputs  Print the files and directories the images are built from.
#   refs    Print one image reference per line.
#
# demo.sh and the workflow both read this file, so a codespace pulls exactly the
# tags the workflow publishes. A tag is "src-" and a hash of the image's build
# inputs at the checked-out commit (git object IDs of its Dockerfile, dependency
# files and build arguments), not of the commit: every commit with the same
# inputs uses the same image, and an image never drifts from the checkout
# whose source compose.yaml mounts into it. Uncommitted changes do not change a
# tag; see `demo.sh build-local`.
#
# QDASH_DEMO_REGISTRY (default ghcr.io/oqtopus-team) selects the registry
# namespace to pull from.
set -euo pipefail

images_repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

# Compose project name and UI label of the demo. The UI image bakes it in.
demo_env="codespaces-demo"
demo_registry="${QDASH_DEMO_REGISTRY:-ghcr.io/oqtopus-team}"
# Bump to rebuild every image when the tag scheme or build settings change.
tag_scheme="qdash-demo-images/v1"

python_inputs="pyproject.toml uv.lock src/qdash/api/pyproject.toml src/qdash/workflow/pyproject.toml clients/python/pyproject.toml clients/python/README.md .dockerignore"

# key|image name|Dockerfile|build arguments (space-separated)|extra inputs.
# The key names the QDASH_DEMO_<KEY>_IMAGE variable of the Compose override.
demo_images=(
  "API|qdash-demo-api|src/qdash/api/Dockerfile||${python_inputs}"
  "DEPLOYMENT_SERVICE|qdash-demo-deployment-service|src/qdash/workflow/Dockerfile.deployment||${python_inputs}"
  "WORKFLOW|qdash-demo-workflow|src/qdash/workflow/Dockerfile||${python_inputs}"
  "UI|qdash-demo-ui|ui/Dockerfile|NEXT_PUBLIC_API_URL=/api NEXT_PUBLIC_ENV=${demo_env} NEXT_PUBLIC_DEFAULT_THEME=light|ui .dockerignore"
)

images_die() {
  printf '[qdash-demo] %s\n' "$*" >&2
  exit 1
}

sha256() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum | cut -d' ' -f1
  else
    shasum -a 256 | cut -d' ' -f1
  fi
}

# image_tag DOCKERFILE "ARGS" "INPUTS": the content tag at HEAD.
image_tag() {
  local dockerfile="$1" args="$2" inputs="$3" path oid
  {
    echo "$tag_scheme"
    echo "dockerfile=${dockerfile}"
    echo "args=${args}"
    for path in "$dockerfile" $inputs; do
      oid="$(git -C "$images_repo_root" rev-parse --verify --quiet "HEAD:${path}")" ||
        images_die "Cannot read ${path} at HEAD of ${images_repo_root}; the demo images need a git checkout"
      echo "${path} ${oid}"
    done
  } | sha256 | cut -c1-20 | sed 's/^/src-/'
}

# for_each_image CALLBACK: CALLBACK key name dockerfile args inputs tag.
for_each_image() {
  local entry key name dockerfile args inputs tag
  # Shows git's own error, such as an untrusted repository owner.
  git -C "$images_repo_root" rev-parse --verify HEAD >/dev/null ||
    images_die "The demo images are named from the git commit of ${images_repo_root}"
  for entry in "${demo_images[@]}"; do
    IFS='|' read -r key name dockerfile args inputs <<<"$entry"
    # A separate assignment, so a failed image_tag stops the script.
    tag="$(image_tag "$dockerfile" "$args" "$inputs")"
    "$1" "$key" "$name" "$dockerfile" "$args" "$inputs" "$tag"
  done
}

print_env() { echo "QDASH_DEMO_$1_IMAGE=\"${demo_registry}/$2:$6\""; }
print_ref() { echo "${demo_registry}/$2:$6"; }
# shellcheck disable=SC2086 # one line per input path
print_inputs() { printf '%s\n' "$3" $5; }

matrix_separator=""
print_matrix_entry() {
  local build_args
  build_args="$(printf '%s' "$4" | tr ' ' '\n' | awk 'NF { printf "%s%s", sep, $0; sep = "\\n" }')"
  printf '%s{"key":"%s","name":"%s","dockerfile":"%s","build_args":"%s","tag":"%s"}' \
    "$matrix_separator" "$1" "$2" "$3" "$build_args" "$6"
  matrix_separator=","
}

images_main() {
  case "${1:-}" in
    env) for_each_image print_env ;;
    refs) for_each_image print_ref ;;
    inputs) for_each_image print_inputs | sort -u ;;
    matrix)
      printf '['
      for_each_image print_matrix_entry
      printf ']\n'
      ;;
    *)
      echo "Usage: $0 env|matrix|inputs|refs" >&2
      exit 2
      ;;
  esac
}

# Run as a command; demo.sh sources the file for its functions instead.
if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  images_main "$@"
fi

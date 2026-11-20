#!/bin/bash
set -euo pipefail

if [[ $# -ne 1 ]]; then
    echo 'Usage: bash deployment/multica-backend/build-release.sh NEW_OUTPUT_DIRECTORY' >&2
    exit 2
fi

here=$(cd -- "$(dirname -- "$0")" && pwd)
repository=$(cd -- "$here/../.." && pwd)
parent=$(cd -- "$(dirname -- "$1")" && pwd)
output="$parent/$(basename -- "$1")"
if [[ -e $output || -L $output ]]; then
    echo 'Output directory must be new.' >&2
    exit 2
fi

temp=$(mktemp -d "${TMPDIR:-/tmp}/multica-backend-build.XXXXXXXX")
trap 'rm -rf -- "$temp"' EXIT
export UV_CACHE_DIR="$temp/uv-cache"
export UV_PROJECT_ENVIRONMENT="$temp/test-venv"
unset UV_INDEX UV_INDEX_URL UV_DEFAULT_INDEX UV_EXTRA_INDEX_URL UV_FIND_LINKS

# Freeze the source snapshot so an edit during tests cannot change the wheel.
mkdir -p "$temp/source/mcp" "$temp/source/scripts" "$temp/release"
cp "$repository/mcp/pyproject.toml" "$temp/source/mcp/"
cp -R "$repository/mcp/multica_backend" "$repository/mcp/tests" "$temp/source/mcp/"
cp "$repository/scripts/check_multica_contract.py" "$temp/source/scripts/"
if [[ -f $repository/mcp/uv.lock ]]; then
    cp "$repository/mcp/uv.lock" "$temp/source/mcp/"
fi

cd "$temp/source/mcp"
if [[ -f uv.lock ]]; then
    uv --no-config lock --check
else
    uv --no-config lock
fi
uv --no-config run --locked --extra test python -B -m unittest discover -s tests -q
uv --no-config export --locked --no-dev --no-emit-project --output-file "$temp/release/requirements.lock.txt" >/dev/null
uv --no-config build --wheel --out-dir "$temp/release"

for asset in install-release.sh run-service.sh multica-backend.service multica-backend.sysusers.conf \
    multica-backend-recover.service multica-backend-recover.timer \
    oauth.env.example config.example.json caddy-route.example verify-route.py; do
    cp "$here/$asset" "$temp/release/"
done

cd "$temp/release"
if command -v sha256sum >/dev/null; then
    sha256sum -- * > SHA256SUMS
else
    shasum -a 256 -- * > SHA256SUMS
fi
mkdir -- "$output"
cp -- ./* "$output/"
printf 'Release prepared at %s\n' "$output"

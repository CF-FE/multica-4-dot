#!/bin/bash
set -euo pipefail

if [[ $# -ne 1 || $1 != /* ]]; then
    echo 'Usage: bash install-release.sh NEW_ABSOLUTE_RELEASE_DIRECTORY' >&2
    exit 2
fi

cd -- "$(dirname -- "$0")"
sha256sum --check SHA256SUMS
wheel=(./multica_backend_mcp-*.whl)
if [[ ${#wheel[@]} -ne 1 || ! -f ${wheel[0]} ]]; then
    echo 'Expected exactly one Multica Backend wheel.' >&2
    exit 2
fi

umask 022
release=$1
mkdir -- "$release"
python3 -m venv "$release/.venv"
release_pip() {
    env -i PATH="$PATH" PIP_CONFIG_FILE=/dev/null "$release/.venv/bin/python" \
        -m pip --disable-pip-version-check "$@"
}
release_pip install --no-cache-dir --index-url https://pypi.org/simple \
    --require-hashes --only-binary=:all: -r requirements.lock.txt
release_pip install --no-cache-dir --no-index --no-deps "${wheel[0]}"
release_pip check
"$release/.venv/bin/python" -B -c 'from multica_backend.server import create_app'
install -m 0755 run-service.sh "$release/run-service.sh"
install -m 0644 SHA256SUMS "$release/source.SHA256SUMS"
printf 'Staged %s\n' "$release"

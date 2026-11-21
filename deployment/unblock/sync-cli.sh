#!/bin/sh
set -eu

# Refresh this host's CLI from its running backend after an upgrade.
container=multica-backend-1
target=/opt/multica-unblock/bin/multica
test "$(docker inspect --format '{{.State.Running}}' "$container")" = true
temporary=$(mktemp "${target}.XXXXXX")
trap 'rm -f "$temporary"' EXIT

docker cp "$container:/app/multica" "$temporary"
chown root:root "$temporary"
chmod 0755 "$temporary"
"$temporary" config show --help >/dev/null
mv -f "$temporary" "$target"

#!/bin/sh
set -eu
set +x

if [ -f "$CREDENTIALS_DIRECTORY/mailbox-token" ]; then
    MULTICA_BACKEND_MAILBOX_ACCESS_TOKEN=$(cat "$CREDENTIALS_DIRECTORY/mailbox-token")
    export MULTICA_BACKEND_MAILBOX_ACCESS_TOKEN
fi

if [ "${1:-}" = recover ]; then
    exec ./.venv/bin/python -B -m multica_backend.recover
fi

# The application currently reads these three OAuth settings from its process
# environment. The systemd unit hands the values over as credential files.
MULTICA_MCP_GITHUB_CLIENT_ID=$(cat "$CREDENTIALS_DIRECTORY/github-client-id")
MULTICA_MCP_GITHUB_CLIENT_SECRET=$(cat "$CREDENTIALS_DIRECTORY/github-client-secret")
MULTICA_MCP_OAUTH_SIGNING_KEY=$(cat "$CREDENTIALS_DIRECTORY/oauth-signing-key")
export MULTICA_MCP_GITHUB_CLIENT_ID MULTICA_MCP_GITHUB_CLIENT_SECRET MULTICA_MCP_OAUTH_SIGNING_KEY

exec ./.venv/bin/multica-backend-mcp

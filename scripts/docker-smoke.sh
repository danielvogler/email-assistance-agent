#!/usr/bin/env bash
# Build the image, start it with placeholder credentials, and check that the
# MCP endpoint lists exactly the nine tools. No mailbox is contacted: listing
# tools needs no IMAP login.
set -euo pipefail

IMAGE="${IMAGE:-email-assistance-agent:smoke}"
PORT="${SMOKE_PORT:-18080}"
NAME="email-assistance-agent-smoke-$$"
EXPECTED="compose_draft create_draft delete_draft list_drafts read_draft read_message read_thread search update_draft"

docker build --tag "$IMAGE" .
docker run --detach --rm --name "$NAME" --publish "127.0.0.1:${PORT}:8080" \
  --env EMAIL_USER=smoke@example.com \
  --env EMAIL_PASSWORD=not-a-real-password \
  --env ALLOWED_HOSTS="localhost:*,127.0.0.1:*" \
  "$IMAGE" >/dev/null
trap 'docker stop "$NAME" >/dev/null 2>&1 || true' EXIT

rpc() {
  curl --silent --show-error --fail \
    --header "Content-Type: application/json" \
    --header "Accept: application/json, text/event-stream" \
    --data "$1" "http://localhost:${PORT}/mcp"
}

for _ in $(seq 1 30); do
  if rpc '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"smoke","version":"0"}}}' >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

ACTUAL=$(rpc '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' \
  | python3 -c 'import json,sys; print(" ".join(sorted(t["name"] for t in json.load(sys.stdin)["result"]["tools"])))')

if [[ "$ACTUAL" != "$EXPECTED" ]]; then
  echo "FAIL: expected tools [$EXPECTED], got [$ACTUAL]" >&2
  docker logs "$NAME" >&2 || true
  exit 1
fi
echo "PASS: image serves exactly the nine tools"

#!/usr/bin/env bash
set -euo pipefail
case "${ROLE:-server}" in
  server)
    exec uv run server/main.py ;;
  client)
    exec uv run client/oracle_mcp_client.py ;;
  *)
    echo "Unknown ROLE=$ROLE (expected 'server' or 'client')" >&2
    exit 1 ;;
esac

#!/bin/sh
set -euo pipefail

# Launch three MCP servers in SSE mode on distinct ports
pdbe-mcp-server --transport sse --server-type pdbe_api_server --port 8010 &
pdbe-mcp-server --transport sse --server-type pdbe_graph_server --port 8020 &
pdbe-mcp-server --transport sse --server-type pdbe_search_server --port 8030 &

# Start nginx in foreground
exec nginx -g 'daemon off;'

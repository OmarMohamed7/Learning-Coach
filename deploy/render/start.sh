#!/bin/sh
# Starts the MCP servers in the background, waits until both accept connections, then runs Chainlit
# in the foreground on Render's $PORT. If the MCP process dies, the container exits so Render restarts it.
set -e
cd /app/learning_coach

python /app/mcp_servers/run_all.py &
MCP_PID=$!

python - <<'PY'
import socket, sys, time
for _ in range(60):
    try:
        for port in (8001, 8002):
            socket.create_connection(("127.0.0.1", port), timeout=1).close()
        sys.exit(0)
    except OSError:
        time.sleep(0.5)
sys.exit("MCP servers did not start within 30s")
PY

chainlit run main.py --host 0.0.0.0 --port "${PORT:-10000}" --headless &
APP_PID=$!

# Exit (and let Render restart us) as soon as either process stops.
while kill -0 "$MCP_PID" 2>/dev/null && kill -0 "$APP_PID" 2>/dev/null; do sleep 5; done
kill "$MCP_PID" "$APP_PID" 2>/dev/null || true
exit 1

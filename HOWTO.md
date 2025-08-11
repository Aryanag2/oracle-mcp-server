# HOWTO: Run the Oracle MCP (Server + Client) Project

This project runs as **two containers** via Docker Compose:

- **oracle-mcp** — your MCP server (`server/main.py`) running as an HTTP service on port 8000
- **mcp-client** — your chat client (`client/oracle_mcp_client.py`) that talks to the server over HTTP and uses Oracle Gen AI

> The client **does not** spawn the server. They're separate processes/containers communicating via HTTP.

---

## Prerequisites

- Docker + Docker Compose
- An Oracle database reachable from your machine/container
- OCI credentials on your host at `~/.oci` (mounted read-only into the client)
  - Since the client code hardcodes model details, you still need valid auth material in `~/.oci`

---

## Repo Layout (expected)

```
.
├─ client/
│  └─ oracle_mcp_client.py
├─ server/
│  └─ main.py
├─ docker-compose.yml
├─ Dockerfile.server
├─ Dockerfile.client
├─ Dockerfile.unified          # optional, not required for two-container flow
├─ .dockerignore
├─ .gitignore
└─ server/.env.example
```

---

## 1) Configure your database connection

Create `server/.env` on your **host** (do not commit it):

```env
ORACLE_CONNECTION_STRING=ADMIN/********@(description= (retry_count=20)(retry_delay=3)(address=(protocol=tcps)(port=1522)(host=adb.us-ashburn-1.oraclecloud.com))(connect_data=(service_name=q9tjyjeyzhxqwla_dmcherka23ai_high.adb.oraclecloud.com))(security=(ssl_server_dn_match=yes)))
TARGET_SCHEMA=
THICK_MODE=0
ORACLE_CLIENT_LIB_DIR=
CACHE_DIR=/var/cache/oracle-mcp
```

**Tips**
- Keep it **one line**, no quotes, no trailing comments.
- Compose reads this file and injects the variables as container env vars.

---

## 2) Build & run

From the repo root:

```bash
docker compose up --build
```

What you should see:
- `oracle-mcp` logs: the HTTP server starts and prints something like  
  `INFO: Uvicorn running on http://0.0.0.0:8000`
- `mcp-client` logs: connects to `http://oracle-mcp:8000`, initializes, loads MCP tools, and shows a prompt.

Stop everything:

```bash
docker compose down
```

---

## 3) Configuration knobs

### Ports & URLs
- Server HTTP port: `8000` (exported in `docker-compose.yml`)
- Client to server URL: `MCP_SERVER_URL=http://oracle-mcp:8000`

### Oracle Client (thick mode)
- The server image already installs **Oracle Instant Client 23.7**.
- To enable thick mode, set `THICK_MODE=1` in `server/.env`.  
  If you need a custom client path, set `ORACLE_CLIENT_LIB_DIR` and ensure `LD_LIBRARY_PATH`.

### OCI credentials (client)
- Your `~/.oci` folder is mounted into the client as read-only.
- The sample client hardcodes:
  - `auth_profile=aryan-chicago`
  - `model_id=openai.gpt-4.1-mini`
  - `service_endpoint=https://inference.generativeai.us-chicago-1.oci.oraclecloud.com`
- You still need valid tokens/keys in `~/.oci` for requests to succeed.

---

## 4) Useful commands

Follow logs:

```bash
docker compose logs -f oracle-mcp
docker compose logs -f mcp-client
```

Rebuild after code changes:

```bash
docker compose build --no-cache
docker compose up
```

Open an interactive shell:

```bash
docker compose exec oracle-mcp bash
docker compose exec mcp-client bash
```

(If your base image doesn't include `bash`, use `sh` instead.)

---

## 5) Testing the MCP server directly

You can test the HTTP MCP server directly using curl or any HTTP client:

```bash
# Test initialization
curl -X POST http://localhost:8000/mcp/v1/messages \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 1,
    "method": "initialize",
    "params": {
      "protocolVersion": "2024-11-05",
      "capabilities": {"roots": {"listChanged": true}, "sampling": {}},
      "clientInfo": {"name": "test-client", "version": "1.0.0"}
    }
  }'

# List available tools
curl -X POST http://localhost:8000/mcp/v1/messages \
  -H "Content-Type: application/json" \
  -d '{
    "jsonrpc": "2.0",
    "id": 2,
    "method": "tools/list",
    "params": {}
  }'
```

---

## 6) Troubleshooting

**Client can't connect (connection refused)**
- Confirm `oracle-mcp` logs show the HTTP server is listening on `0.0.0.0:8000`.
- Make sure the server container is healthy: `docker compose ps`
- Verify the service name in docker-compose matches the URL in the client (`oracle-mcp`)

**ORA-/connect errors**
- Verify `ORACLE_CONNECTION_STRING` in `server/.env` (host, port, service name, TCPS).
- If using TCPS (ADB), confirm outbound 1522 is open on your network.

**OCI auth errors**
- Check `~/.oci/config` and tokens. The client mounts `~/.oci` from the host.
- Ensure the hardcoded profile name exists in your config.

**Module not found (`httpx`, `langchain`, etc.)**
- Ensure `pyproject.toml` includes needed deps; rebuild with `--no-cache`.
- The images run `uv sync --frozen` at build time; if deps changed, rebuild.

**HTTP 404 or invalid JSON errors**
- The server expects MCP protocol messages at `/mcp/v1/messages` endpoint
- Ensure you're sending proper JSON-RPC 2.0 formatted requests
- Check server logs for detailed error messages

**MCP tools not loading**
- Check that the server started successfully and the database connection works
- Verify the tools/list endpoint returns the expected tools
- Look for database initialization errors in the server logs

---

## 7) Optional: Single-image (not required here)

If you ever want the client to spawn the server in a **single** container, you can use `Dockerfile.unified` and run with `-e ROLE=client` and `LOCAL_SPAWN=1`. This is **not** used in the two-container setup.

---

## 8) Local (no Docker)

If you want to run locally:

```bash
# In one terminal (server):
cd server
export ORACLE_CONNECTION_STRING="..."
uv run python main.py  # starts HTTP server on localhost:8000

# In another terminal (client):
cd client
export MCP_SERVER_URL=http://localhost:8000
uv run python oracle_mcp_client.py
```

---

## 9) Quick checklist

- [ ] `server/.env` exists on host with the correct connection string  
- [ ] `server/main.py` present; server starts HTTP service on port 8000
- [ ] `~/.oci` exists with the profile used by the client  
- [ ] `docker compose up --build` shows server HTTP listening and client tools loaded
- [ ] Client can connect to `http://oracle-mcp:8000/mcp/v1/messages`

---

## 10) Architecture Notes

**HTTP MCP Protocol**
- The server runs as a standard HTTP service using FastMCP and Uvicorn
- Client communicates using JSON-RPC 2.0 over HTTP POST requests
- All MCP protocol messages go to the `/mcp/v1/messages` endpoint
- This is simpler and more standard than WebSocket-based communication

**Container Communication**
- Both containers are on the same Docker network
- Client uses the service name `oracle-mcp` to reach the server
- Port 8000 is exposed for external access if needed

Happy hacking 🚀
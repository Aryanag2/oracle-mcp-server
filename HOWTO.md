# HOWTO: Run the Oracle MCP Server

This project now uses a **single container** via Docker Compose to host the MCP
server. Run your client directly on your machine (or any other host) and point
it to the server's HTTP endpoint.

> The server runs inside Docker; the client runs outside and communicates over
> HTTP.

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
├─ Dockerfile.unified          # optional
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
docker compose up --build -d
```

This builds the image and starts the `oracle-mcp` service in the background.
The server listens on port `8000` and is mapped to the same port on the host.

If you're running on a cloud compute instance, make sure your firewall or
security groups allow inbound traffic on port `8000`. External clients can then
connect using `http://<public-ip>:8000/mcp/`.

Stop the container:

```bash
docker compose down
```

---

## 3) Configuration knobs

### Ports & URLs
- Server HTTP port: `8000` (exported in `docker-compose.yml`)

### Oracle Client (thick mode)
- The server image already installs **Oracle Instant Client 23.7**.
- To enable thick mode, set `THICK_MODE=1` in `server/.env`.  
  If you need a custom client path, set `ORACLE_CLIENT_LIB_DIR` and ensure `LD_LIBRARY_PATH`.

### OCI credentials (client)
Run the Python client directly on your host and ensure it has access to your
OCI credentials at `~/.oci`. Point the client to the server's public URL, for
example:

```bash
export MCP_SERVER_URL="http://<public-ip>:8000"
python client/oracle_mcp_client.py
```

---

## 4) Useful commands

Follow logs:

```bash
docker compose logs -f oracle-mcp
```

Rebuild after code changes:

```bash
docker compose build --no-cache
docker compose up
```

Open an interactive shell:

```bash
docker compose exec oracle-mcp bash
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
- If connecting from another machine, ensure your firewall or security group allows inbound traffic on port `8000` and that your client uses the correct public IP.

**ORA-/connect errors**
- Verify `ORACLE_CONNECTION_STRING` in `server/.env` (host, port, service name, TCPS).
- If using TCPS (ADB), confirm outbound 1522 is open on your network.

**OCI auth errors**
- Check `~/.oci/config` and tokens. Ensure the profile name expected by the client exists in your config.

**Module not found (`httpx`, `langchain`, etc.)**
- Ensure `pyproject.toml` includes needed deps; rebuild with `--no-cache`.
- The image runs `uv sync --frozen` at build time; if deps changed, rebuild.

**HTTP 404 or invalid JSON errors**
- The server expects MCP protocol messages at `/mcp/v1/messages` endpoint
- Ensure you're sending proper JSON-RPC 2.0 formatted requests
- Check server logs for detailed error messages

**MCP tools not loading**
- Check that the server started successfully and the database connection works.
- Verify the `tools/list` endpoint returns the expected tools.
- Look for database initialization errors in the server logs.

---
Happy hacking 🚀

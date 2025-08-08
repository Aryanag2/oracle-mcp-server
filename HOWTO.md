# HOWTO: Run the Oracle MCP (Server + Client) Project

This project runs as **two containers** via Docker Compose:

- **mcp-server** — launches your existing `server/main.py` behind a tiny WebSocket bridge (`ws_bridge.py`).  
- **mcp-client** — your chat client (`client/oracle_mcp_client.py`) that talks to the server over WebSocket and uses Oracle Gen AI.

> The client **does not** spawn the server. They’re separate processes/containers.

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
│  ├─ main.py
│  └─ ws_bridge.py
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
- `mcp-server` logs: the WebSocket bridge prints something like  
  `[ws_bridge] listening on ws://0.0.0.0:8765`
- `mcp-client` logs: connects to `ws://mcp-server:8765`, initializes, loads MCP tools, and shows a prompt.

Stop everything:

```bash
docker compose down
```

---

## 3) Configuration knobs

### Ports & URLs
- Server WS port: `8765` (exported in `docker-compose.yml`)
- Client to server URL: `MCP_SERVER_WS_URL=ws://mcp-server:8765`

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
docker compose logs -f mcp-server
docker compose logs -f mcp-client
```

Rebuild after code changes:

```bash
docker compose build --no-cache
docker compose up
```

Open an interactive shell:

```bash
docker compose exec mcp-server bash
docker compose exec mcp-client bash
```

(If your base image doesn’t include `bash`, use `sh` instead.)

---

## 5) Healthcheck note

If your server image doesn’t have `bash`, switch the healthcheck to Python:

```yaml
healthcheck:
  test: ["CMD-SHELL", "python -c "import socket; s=socket.create_connection(('127.0.0.1',8765),3); s.close()""]
  interval: 10s
  timeout: 3s
  retries: 20
```

Or install `bash` in `Dockerfile.server`.

---

## 6) Troubleshooting

**Client can’t connect (healthcheck failing / connection refused)**
- Confirm `mcp-server` logs show the bridge is listening on `0.0.0.0:8765`.
- Make sure `ws_bridge.py` is present and the server `CMD` is:
  ```dockerfile
  CMD ["uv", "run", "server/ws_bridge.py"]
  ```

**ORA-/connect errors**
- Verify `ORACLE_CONNECTION_STRING` in `server/.env` (host, port, service name, TCPS).
- If using TCPS (ADB), confirm outbound 1522 is open on your network.

**OCI auth errors**
- Check `~/.oci/config` and tokens. The client mounts `~/.oci` from the host.
- Ensure the hardcoded profile name exists in your config.

**Module not found (`websockets`, `langchain`, etc.)**
- Ensure `pyproject.toml` includes needed deps; rebuild with `--no-cache`.
- The images run `uv sync --frozen` at build time; if deps changed, rebuild.

**Invalid JSON / protocol issues**
- The bridge passes one JSON message per WebSocket frame.
- Make sure your MCP server prints **newline-delimited JSON** responses (which the bridge forwards as frames).

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
uv run python ws_bridge.py  # listens on ws://localhost:8765

# In another terminal (client):
cd client
export MCP_SERVER_WS_URL=ws://localhost:8765
uv run python oracle_mcp_client.py
```

---

## 9) Quick checklist

- [ ] `server/.env` exists on host with the correct connection string  
- [ ] `server/ws_bridge.py` present; server `CMD` points to it  
- [ ] `~/.oci` exists with the profile used by the client  
- [ ] `docker compose up --build` shows server WS listening and client tools loaded

Happy hacking 🚀

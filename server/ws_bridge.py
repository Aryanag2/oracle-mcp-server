# server/ws_bridge.py
import asyncio
import json
import os
from pathlib import Path

import websockets

SERVER_DIR = Path(__file__).parent
CMD = ["uv", "run", "main.py"]  # your existing server entry

async def handle_client(websocket):
    # Start the MCP server subprocess (stdio)
    proc = await asyncio.create_subprocess_exec(
        *CMD,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=str(SERVER_DIR),
    )

    async def ws_to_stdin():
        try:
            async for msg in websocket:
                # Expect JSON text messages; forward as a single line to MCP
                if isinstance(msg, (bytes, bytearray)):
                    data = msg
                else:
                    data = (msg.rstrip("\n") + "\n").encode("utf-8")
                proc.stdin.write(data)
                await proc.stdin.drain()
        except Exception:
            pass
        finally:
            if proc.stdin:
                proc.stdin.close()

    async def stdout_to_ws():
        try:
            while True:
                line = await proc.stdout.readline()
                if not line:
                    break
                await websocket.send(line.decode("utf-8").rstrip("\n"))
        except Exception:
            pass

    async def stderr_log():
        # Optional: just drain stderr to avoid deadlocks; you can print it if you like
        while True:
            chunk = await proc.stderr.read(4096)
            if not chunk:
                break

    # Run pumps
    tasks = [
        asyncio.create_task(ws_to_stdin()),
        asyncio.create_task(stdout_to_ws()),
        asyncio.create_task(stderr_log()),
    ]
    done, pending = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    for t in pending:
        t.cancel()

    try:
        await proc.wait()
    except Exception:
        proc.kill()

async def main():
    port = int(os.getenv("MCP_WS_PORT", "8765"))
    async with websockets.serve(handle_client, "0.0.0.0", port):
        print(f"[ws_bridge] listening on ws://0.0.0.0:{port}")
        await asyncio.Future()

if __name__ == "__main__":
    asyncio.run(main())

import asyncio
import websockets

async def check():
    async with websockets.connect("ws://127.0.0.1:8765"):
        pass

if __name__ == "__main__":
    asyncio.run(check())

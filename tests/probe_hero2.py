"""Test widoczności hero: manipulacje na żywo + zrzuty."""
import asyncio
import base64
import json
import time
from pathlib import Path

import httpx
import websockets

CDP_PORT = 9222
BASE = "http://127.0.0.1:8000"
OUT = Path(__file__).resolve().parent / "shots"


async def main() -> None:
    async with httpx.AsyncClient() as c:
        pages = (await c.get(f"http://127.0.0.1:{CDP_PORT}/json/list")).json()
    page = next((p for p in pages if p["type"] == "page"), None)
    async with websockets.connect(page["webSocketDebuggerUrl"], max_size=2**26) as ws:
        mid = 0

        async def send(method, params=None):
            nonlocal mid
            mid += 1
            await ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
            while True:
                msg = json.loads(await ws.recv())
                if msg.get("id") == mid:
                    return msg

        async def ev(expr):
            r = await send("Runtime.evaluate", {"expression": expr, "returnByValue": True})
            return r.get("result", {}).get("result", {}).get("value")

        async def shot(name):
            r = await send("Page.captureScreenshot", {"format": "jpeg", "quality": 85, "captureBeyondViewport": False})
            (OUT / name).write_bytes(base64.b64decode(r["result"]["data"]))
            print("shot:", name)

        async def wait_js(cond, timeout=15):
            t0 = time.time()
            while time.time() - t0 < timeout:
                if await ev(cond):
                    return True
                await asyncio.sleep(0.3)
            return False

        await send("Runtime.enable")
        await send("Page.enable")
        await send("Emulation.setDeviceMetricsOverride",
                   {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False})
        await send("Page.navigate", {"url": BASE + "/"})
        await wait_js("document.querySelector('.hero-title .l') && !document.querySelector('#preloader')")
        await asyncio.sleep(0.6)
        await shot("h0-oryginal.jpg")

        await ev("document.querySelector('.hero-media img').style.filter='none';"
                 "document.querySelector('.hero-media').style.zIndex='1';'ok'")
        await asyncio.sleep(0.5)
        await shot("h1-bez-filtra-z1.jpg")

        await ev("document.querySelector('.hero-media').style.zIndex='1';"
                 "document.querySelector('.hero-media img').style.filter='none';"
                 "const a=document.querySelector('.hero-media::after');'ok'")
        await ev("(() => {const h=document.querySelector('.hero-media');"
                 "h.style.setProperty('background','transparent');"
                 "return getComputedStyle(h,'::after').background;})()")
        await asyncio.sleep(0.3)
        await shot("h2-po-after.jpg")


asyncio.run(main())

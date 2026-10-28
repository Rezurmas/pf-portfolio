"""Zrzut sekcji O mnie na home."""
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

        async def wait_js(cond, timeout=15):
            t0 = time.time()
            while time.time() - t0 < timeout:
                try:
                    if await ev(cond):
                        return True
                except Exception:
                    pass
                await asyncio.sleep(0.3)
            return False

        await send("Runtime.enable")
        await send("Page.enable")
        await send("Emulation.setDeviceMetricsOverride",
                   {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False})
        await send("Page.navigate", {"url": BASE + "/"})
        await wait_js("document.querySelector('.hero-title .l') && !document.querySelector('#preloader')")
        await asyncio.sleep(1.0)

        # scroll do sekcji o mnie, daj czas na reveal, zrzut
        await ev("document.querySelector('#about').scrollIntoView()")
        await asyncio.sleep(1.4)
        r = await send("Page.captureScreenshot", {"format": "jpeg", "quality": 85, "captureBeyondViewport": False})
        (OUT / "14-about.jpg").write_bytes(base64.b64decode(r["result"]["data"]))
        print("shot: 14-about.jpg")
        print("about-lead paragrafy:", await ev("document.querySelectorAll('.about-lead p').length"))
        print("about-sign:", await ev("document.querySelector('.about-sign')?.textContent"))
        print("lead tekst:", await ev("document.querySelector('.about-lead p.lead')?.textContent.slice(0,80)"))


asyncio.run(main())

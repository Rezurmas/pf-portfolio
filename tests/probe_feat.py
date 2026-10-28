"""Probe: featured grid geometria + duration albumow + tla sekcji."""
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
            res = r.get("result", {})
            if res.get("exceptionDetails"):
                return "EXC: " + str(res["exceptionDetails"].get("exception", {}).get("description", ""))[:150]
            return res.get("result", {}).get("value")

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
        await asyncio.sleep(0.5)

        # geometria featured
        await ev("document.querySelector('.feature-grid').scrollIntoView({block:'center'})")
        await asyncio.sleep(1.6)
        geo = await ev(
            "(() => {const wrap=document.querySelector('.feature-grid').getBoundingClientRect().width;"
            "const cells=[...document.querySelectorAll('.fcell')].map(c=>{const r=c.getBoundingClientRect();"
            "return {w: Math.round(r.width), h: Math.round(r.height), cls: c.className.replace('fcell','').trim()};});"
            "return JSON.stringify({gridW: Math.round(wrap), cells});})()"
        )
        print("featured:", geo)

        # duration albumow
        dur = await ev("getComputedStyle(document.querySelector('.album-row')).transitionDuration")
        print("album-row transition-duration:", dur)

        # tla sekcji
        bgs = await ev(
            "JSON.stringify({about: getComputedStyle(document.querySelector('#about')).backgroundColor,"
            " albumSec: getComputedStyle(document.querySelectorAll('.sec')[2] || document.querySelector('#about')).backgroundColor})"
        )
        print("tla:", bgs)

        # zrzut featured
        r = await send("Page.captureScreenshot", {"format": "jpeg", "quality": 85, "captureBeyondViewport": False})
        (OUT / "15-featured.jpg").write_bytes(base64.b64decode(r["result"]["data"]))
        print("shot: 15-featured.jpg")


asyncio.run(main())

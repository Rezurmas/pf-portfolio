"""Sonda: reload home po mobile — czemu brak .hero-title .l?"""
import asyncio
import json
import time

import httpx
import websockets

CDP_PORT = 9222
BASE = "http://127.0.0.1:8000"


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
                return "EXC: " + str(res["exceptionDetails"].get("exception", {}).get("description"))[:150]
            return res.get("result", {}).get("value")

        await send("Runtime.enable")
        await send("Page.enable")
        await send("Emulation.setDeviceMetricsOverride",
                   {"width": 390, "height": 844, "deviceScaleFactor": 1, "mobile": True})
        await send("Page.navigate", {"url": BASE + "/"})
        await asyncio.sleep(2.5)
        print("mobile:", await ev("JSON.stringify({hero: !!document.querySelector('.hero'), l: document.querySelectorAll('.hero-title .l').length, vlen: document.querySelector('#view').innerHTML.length, pre: !!document.querySelector('#preloader')})"))

        await send("Emulation.setDeviceMetricsOverride",
                   {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False})
        await send("Page.navigate", {"url": BASE + "/"})
        for i in range(8):
            await asyncio.sleep(0.8)
            st = await ev("JSON.stringify({ready: document.readyState, hero: !!document.querySelector('.hero'), l: document.querySelectorAll('.hero-title .l').length, vlen: document.querySelector('#view').innerHTML.length, pre: !!document.querySelector('#preloader'), ssite: !!(window.S && S.site)})")
            print(f"desktop t={i*0.8:.1f}s:", st)
            if '"l":' in st and '"l":0' not in st:
                break


asyncio.run(main())

"""Sanity: 320px viewport — scrollWidth ma byc 320, hero bez ucieczki."""
import asyncio
import json

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
            r = await send("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True})
            res = r.get("result", {})
            if res.get("exceptionDetails"):
                return "EXC: " + str(res["exceptionDetails"].get("exception", {}).get("description", ""))[:150]
            return res.get("result", {}).get("value")

        await send("Emulation.setDeviceMetricsOverride",
                   {"width": 320, "height": 568, "deviceScaleFactor": 2, "mobile": True,
                    "screenWidth": 320, "screenHeight": 568})
        await send("Page.navigate", {"url": BASE + "/"})
        await asyncio.sleep(2.5)
        print("320px: scrollWidth vs clientWidth:",
              await ev("document.documentElement.scrollWidth + ' vs ' + document.documentElement.clientWidth"))
        print("hero title rect:",
              await ev("(() => {const r = document.querySelector('.hero-title').getBoundingClientRect(); return Math.round(r.right) + ' (viewport 320)';})()"))
        print("naglowek rect:",
              await ev("(() => {const r = document.querySelector('.nav-bar').getBoundingClientRect(); return Math.round(r.right) + ' (viewport 320)';})()"))


asyncio.run(main())

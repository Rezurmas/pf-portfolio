"""Mobile: siatka wyroznionych po fixie — rowne kwadraty, brak szarych blokow."""
import asyncio
import base64
import json
import time

import httpx
import websockets

CDP_PORT = 9222
BASE = "http://127.0.0.1:8000"
SHOTS = "C:/Users/Dawid/Desktop/portfolio/tests/shots"


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

        async def shot(name):
            r = await send("Page.captureScreenshot", {"format": "jpeg", "quality": 82})
            with open(f"{SHOTS}/{name}", "wb") as f:
                f.write(base64.b64decode(r["result"]["data"]))
            print("shot:", name)

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
                   {"width": 390, "height": 844, "deviceScaleFactor": 2, "mobile": True,
                    "screenWidth": 390, "screenHeight": 844})
        await send("Page.navigate", {"url": BASE + "/"})
        await wait_js("document.querySelectorAll('.feature-grid .fcell').length > 0 && !document.querySelector('#preloader')")
        await asyncio.sleep(1.0)
        await ev("window.scrollTo(0, document.querySelector('.feature-grid').getBoundingClientRect().top + scrollY - 40)")
        await asyncio.sleep(2.5)
        print("kafle (wys x szer):", await ev(
            "[...document.querySelectorAll('.feature-grid .fcell')].map(c => {"
            "  const r = c.getBoundingClientRect(); return Math.round(r.width) + 'x' + Math.round(r.height);"
            "}).join(' | ')"
        ))
        print("grid bg:", await ev("getComputedStyle(document.querySelector('.feature-grid')).backgroundColor"))
        await shot("d1-featured-fixed.jpg")


asyncio.run(main())

"""Probe: webp picture, wymiary, lightbox webp, zero bledow."""
import asyncio
import json
import time

import httpx
import websockets

CDP_PORT = 9222
BASE = "http://127.0.0.1:8000"
errors: list[str] = []


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
                m = msg.get("method")
                if m == "Runtime.exceptionThrown":
                    errors.append("exc")
                if m == "Runtime.consoleAPICalled" and msg["params"].get("type") == "error":
                    errors.append("console.error")
                if m == "Log.entryAdded" and msg["params"]["entry"].get("level") == "error":
                    errors.append("log.error: " + msg["params"]["entry"].get("text", "")[:100])

        async def ev(expr):
            r = await send("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True})
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
        await send("Log.enable")
        await send("Page.enable")
        await send("Emulation.setDeviceMetricsOverride",
                   {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False})
        await send("Page.navigate", {"url": BASE + "/"})
        await wait_js("document.querySelector('.hero-title .l') && !document.querySelector('#preloader')")
        await asyncio.sleep(0.5)

        # home: featured picture + dims
        print("featured picture:", await ev("document.querySelectorAll('.feature-grid picture').length"))
        print("featured source webp:", await ev(
            "!!document.querySelector('.feature-grid source[type=\"image/webp\"]')"))
        print("featured img width attr:", await ev(
            "document.querySelector('.feature-grid img').getAttribute('width')"))

        # album: masonry
        await ev("PF.navigate('/portfolio/rajd'); 'ok'")
        await wait_js("document.querySelectorAll('.mcell').length === 14")
        print("masonry picture:", await ev("document.querySelectorAll('.masonry picture').length"))
        print("masonry img width:", await ev("document.querySelector('.masonry img').getAttribute('width')"))

        # lightbox: webp
        await ev("document.querySelector('.mcell').click()")
        await wait_js("document.querySelector('#lightbox').classList.contains('open') && document.querySelector('#lb-img').naturalWidth > 0")
        src = await ev("document.querySelector('#lb-img').getAttribute('src')")
        print("lightbox src (webp?):", src)

        # album cover picture na portfolio
        await ev("document.querySelector('#lb-close').click()")
        await ev("PF.navigate('/portfolio'); 'ok'")
        await wait_js("document.querySelectorAll('.album-row').length === 4")
        print("album cover picture:", await ev("document.querySelectorAll('.album-row picture').length"))

        await asyncio.sleep(0.5)
        print("bledy konsoli:", len(errors), errors[:5])


asyncio.run(main())

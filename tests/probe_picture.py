"""Weryfikacja: picture wypełnia kadry + link wyjścia z logowania."""
import asyncio
import base64
import json
import os
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
        await asyncio.sleep(1.5)

        # 1) kadry featured: img wypełnia komórkę?
        fill = await ev(
            "[...document.querySelectorAll('.feature-grid .fcell')].slice(0, 5).map(cell => {"
            "  const c = cell.getBoundingClientRect();"
            "  const img = cell.querySelector('img');"
            "  const i = img.getBoundingClientRect();"
            "  return Math.round(i.width) + 'x' + Math.round(i.height) + ' vs ' + Math.round(c.width) + 'x' + Math.round(c.height);"
            "}).join(' | ')"
        )
        print("kadry featured (img vs cell):", fill)
        await ev("window.scrollTo(0, document.querySelector('.feature-grid').getBoundingClientRect().top + scrollY - 60)")
        await asyncio.sleep(1.0)
        await shot("c1-featured-mobile.jpg")

        # 2) okładki albumów
        await ev("PF.navigate('/portfolio'); 'ok'")
        await wait_js("document.querySelectorAll('.album-row').length === 4")
        await asyncio.sleep(1.0)
        cover = await ev(
            "[...document.querySelectorAll('.album-cover')].map(c => {"
            "  const r = c.getBoundingClientRect(); const i = c.querySelector('img').getBoundingClientRect();"
            "  return Math.round(i.width) + 'x' + Math.round(i.height) + ' vs ' + Math.round(r.width) + 'x' + Math.round(r.height);"
            "}).join(' | ')"
        )
        print("okladki (img vs cover):", cover)

        # 3) login: link wyjścia
        await ev("PF.navigate('/admin'); 'ok'")
        await wait_js("document.querySelector('#login-form') !== null || document.querySelector('.admin-shell') !== null")
        if await ev("!!document.querySelector('#login-form')"):
            print("link wyjscia:", await ev("document.querySelector('.login-back') !== null"))
            await ev("document.querySelector('.login-back').click()")
            await asyncio.sleep(1.5)
            print("po kliku:", await ev("location.pathname + ' hero=' + !!document.querySelector('.hero')"))
        else:
            print("sesja aktywna — test linku: wyloguj najpierw")
            await ev("document.querySelector('#a-logout').click()")
            await asyncio.sleep(1.0)
            print("login-back po wylogowaniu:", await ev("document.querySelector('.login-back') !== null"))


asyncio.run(main())

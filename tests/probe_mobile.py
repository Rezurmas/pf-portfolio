"""Mobile probe: zrzuty strony na wymiarach telefonu + raport overflow/scaling."""
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
        await send("Emulation.setTouchEmulationEnabled", {"enabled": True})

        await send("Page.navigate", {"url": BASE + "/"})
        await wait_js("document.querySelector('.hero') && !document.querySelector('#preloader')")
        await asyncio.sleep(2.0)

        # metryki: czy strona jest szersza niz viewport (overflow = przyczyna zlego scalowania)
        print("viewport visual:", await ev("window.visualViewport.width"))
        print("scrollWidth vs clientWidth:", await ev("document.documentElement.scrollWidth + ' vs ' + document.documentElement.clientWidth"))
        overflowers = await ev(
            "[...document.querySelectorAll('*')].filter(el => el.getBoundingClientRect().right > window.innerWidth + 2 || el.getBoundingClientRect().left < -2).slice(0,12).map(el => el.tagName + '.' + (el.className && typeof el.className === 'string' ? el.className.split(' ')[0] : '') + ' r=' + Math.round(el.getBoundingClientRect().right)).join(', ')"
        )
        print("overflowery:", overflowers or "brak")
        await shot("m1-home-top.jpg")

        # scroll w dol: featured + albumy
        await ev("window.scrollTo(0, document.querySelector('.sec-head').getBoundingClientRect().top + scrollY + 200)")
        await asyncio.sleep(1.0)
        await shot("m2-home-about.jpg")
        await ev("window.scrollBy(0, 900)")
        await asyncio.sleep(1.0)
        await shot("m3-home-featured.jpg")
        await ev("window.scrollBy(0, 900)")
        await asyncio.sleep(1.0)
        await shot("m4-home-albums.jpg")

        # album
        await ev("PF.navigate('/portfolio/rajd'); 'ok'")
        await wait_js("document.querySelectorAll('.mcell').length === 14")
        await asyncio.sleep(1.0)
        await ev("window.scrollTo(0, 0)")
        await asyncio.sleep(0.5)
        await shot("m5-album-top.jpg")
        await ev("window.scrollBy(0, 800)")
        await asyncio.sleep(1.0)
        await shot("m6-album-masonry.jpg")


asyncio.run(main())

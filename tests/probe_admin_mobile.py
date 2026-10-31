"""Admin na mobile: zrzuty wszystkich sekcji + raport overflow."""
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
        await send("Emulation.setTouchEmulationEnabled", {"enabled": True})
        await send("Page.navigate", {"url": BASE + "/admin"})
        await wait_js("document.querySelector('#login-form') !== null || document.querySelector('.admin-shell') !== null")
        if await ev("!!document.querySelector('#login-form')"):
            pw = os.environ.get("PF_ADMIN_PASS", "admin")
            await ev(f"(() => {{const f=document.querySelector('#login-form');"
                     f"document.querySelector('#a-pass').value={json.dumps(pw)};f.requestSubmit();}})()")
        await wait_js("document.querySelector('.admin-shell') !== null")
        await asyncio.sleep(0.8)
        print("scrollWidth:", await ev("document.documentElement.scrollWidth + ' vs ' + document.documentElement.clientWidth"))
        await shot("a1-dash.jpg")

        await ev("document.querySelector('[data-sec=\"albums\"]').click()")
        await wait_js("document.querySelectorAll('#albums-list .a-row').length === 4")
        await asyncio.sleep(0.5)
        await shot("a2-albums.jpg")

        await ev("document.querySelector('#albums-list .a-row').click()")
        await wait_js("document.querySelector('#a-photo-grid .a-photo') !== null")
        await asyncio.sleep(0.5)
        await shot("a3-editor.jpg")

        await ev("document.querySelector('[data-sec=\"featured\"]').click()")
        await wait_js("document.querySelector('#feat-preview-grid .fcell') !== null")
        await asyncio.sleep(0.6)
        await shot("a4-featured.jpg")

        await ev("document.querySelector('[data-sec=\"messages\"]').click()")
        await asyncio.sleep(0.6)
        await shot("a5-messages.jpg")
        await ev("document.querySelector('[data-sec=\"settings\"]').click()")
        await asyncio.sleep(0.6)
        await shot("a6-settings.jpg")


asyncio.run(main())

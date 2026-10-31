"""Test PRAWDZIWEGO przewijania dotykiem (Input.dispatchTouchEvent)."""
import asyncio
import json
import os
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

        async def touch_drag(x0, y0, x1, y1, steps=8):
            await send("Input.dispatchTouchEvent", {"type": "touchStart",
                                                    "touchPoints": [{"x": x0, "y": y0, "id": 1, "radiusX": 4, "radiusY": 4, "force": 1}]})
            for i in range(1, steps + 1):
                x = x0 + (x1 - x0) * i / steps
                y = y0 + (y1 - y0) * i / steps
                await send("Input.dispatchTouchEvent", {"type": "touchMove",
                                                        "touchPoints": [{"x": x, "y": y, "id": 1, "radiusX": 4, "radiusY": 4, "force": 1}]})
                await asyncio.sleep(0.05)
            await send("Input.dispatchTouchEvent", {"type": "touchEnd", "touchPoints": []})
            await asyncio.sleep(0.4)

        await send("Runtime.enable")
        await send("Page.enable")
        await send("Emulation.setDeviceMetricsOverride",
                   {"width": 390, "height": 844, "deviceScaleFactor": 2, "mobile": True,
                    "screenWidth": 390, "screenHeight": 844})
        await send("Emulation.setTouchEmulationEnabled", {"enabled": True, "maxTouchPoints": 5})
        await send("Page.navigate", {"url": BASE + "/"})
        await wait_js("document.querySelector('.hero') && !document.querySelector('#preloader')")
        await asyncio.sleep(1.5)

        # 1) strona: dotykowy scroll w gore
        y0 = await ev("window.scrollY")
        await touch_drag(195, 700, 195, 300)
        y1 = await ev("window.scrollY")
        print(f"strona: scrollY {y0} -> {y1} (zmienilo sie: {y1 != y0})")

        # 2) pasek wybranych (featured): dotyk w poziomie
        await send("Page.navigate", {"url": BASE + "/admin"})
        await wait_js("document.querySelector('#login-form') !== null || document.querySelector('.admin-shell') !== null")
        if await ev("!!document.querySelector('#login-form')"):
            pw = os.environ.get("PF_ADMIN_PASS", "admin")
            await ev(f"(() => {{const f=document.querySelector('#login-form');"
                     f"document.querySelector('#a-pass').value={json.dumps(pw)};f.requestSubmit();}})()")
        await wait_js("document.querySelector('.admin-shell') !== null")
        await ev("document.querySelector('[data-sec=\"featured\"]').click()")
        await wait_js("document.querySelector('#feat-preview-grid .fcell') !== null")
        await asyncio.sleep(0.6)
        strip = await ev(
            "(() => {const s=document.querySelector('#feat-selected'); const r=s.getBoundingClientRect();"
            "return JSON.stringify({scrollable: s.scrollWidth > s.clientWidth, x: Math.round(r.left + r.width/2), y: Math.round(r.top + r.height/2)});})()"
        )
        print("pasek:", strip)
        st = json.loads(strip)
        s0 = await ev("document.querySelector('#feat-selected').scrollLeft")
        await touch_drag(st["x"], st["y"], st["x"] - 120, st["y"])
        s1 = await ev("document.querySelector('#feat-selected').scrollLeft")
        print(f"pasek wybranych: scrollLeft {s0} -> {s1} (zmienilo sie: {s1 != s0})")


asyncio.run(main())

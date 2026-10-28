"""Probe: album row aktywuje sie zanim wejdzie w ekran (wczesniejsza strefa)."""
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
        await asyncio.sleep(0.6)

        # ustaw pierwszy wiersz albumow tuz POD krawedzia ekranu (~40px ponizej dolu)
        await ev(
            "(() => {const row=document.querySelector('.album-row');"
            "const y=row.getBoundingClientRect().top + scrollY;"
            "scrollTo(0, y - innerHeight + 40);})()"
        )
        await asyncio.sleep(1.8)
        st = await ev(
            "(() => {const row=document.querySelector('.album-row');const r=row.getBoundingClientRect();"
            "return JSON.stringify({rowTop: Math.round(r.top), vh: innerHeight,"
            " isIn: row.classList.contains('is-in'), rowBottom: Math.round(r.bottom)});})()"
        )
        print("album row pod krawedzia ekranu:", st)


asyncio.run(main())

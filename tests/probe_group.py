"""Probe: grupa featured + wczesniejsza strefa aktywacji albumow."""
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

        # stan poczatkowy: kadry featured jeszcze nieaktywne
        print("featured is-in przed scrollem:",
              await ev("document.querySelectorAll('.feature-grid .fcell.is-in').length"))

        # scroll: sam wierzch sekcji featured wjezdza od dolu (top sekcji = 88% wysokosci ekranu)
        await ev(
            "(() => {const s=document.querySelector('section[data-reveal-group]');"
            "scrollTo(0, s.offsetTop - innerHeight*0.88);})()"
        )
        await asyncio.sleep(2.0)
        print("featured is-in po wejsciu sekcji (ma byc 6):",
              await ev("document.querySelectorAll('.feature-grid .fcell.is-in').length"))
        print("top sekcji featured:", await ev(
            "document.querySelector('section[data-reveal-group]').getBoundingClientRect().top.toFixed(0)"))

        # sekcja albumy: sprawdz czy wiersze aktywuja sie ZANIM w pelni wejda w ekran
        await ev("scrollTo(0, 0)")
        await asyncio.sleep(0.4)
        await ev(
            "(() => {const secs=document.querySelectorAll('section');"
            "const as=[...secs].find(s=>s.querySelector('.album-row'));"
            "window.__albSec=as; scrollTo(0, as.offsetTop - innerHeight + 150);})()"
        )
        await asyncio.sleep(1.5)
        st = await ev(
            "(() => {const as=window.__albSec;const row=as.querySelector('.album-row');"
            "const r=row.getBoundingClientRect();"
            "return JSON.stringify({rowTop: Math.round(r.top), vh: innerHeight, isIn: row.classList.contains('is-in'),"
            " secTop: Math.round(as.getBoundingClientRect().top)});})()"
        )
        print("albumy: wiersz przed wejsciem w ekran:", st)


asyncio.run(main())

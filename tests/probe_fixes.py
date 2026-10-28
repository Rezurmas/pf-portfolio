"""Probe fixów: proporcje masonry, liczba featured na home, picker (filtr/grupy/strzałki)."""
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

        await send("Runtime.enable")
        await send("Page.enable")
        await send("Emulation.setDeviceMetricsOverride",
                   {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False})

        # 1) home: ile komórek featured
        await send("Page.navigate", {"url": BASE + "/"})
        await wait_js("document.querySelectorAll('.feature-grid .fcell').length > 0 && !document.querySelector('#preloader')")
        await asyncio.sleep(1.0)
        print("featured na home:", await ev("document.querySelectorAll('.feature-grid .fcell').length"))

        # 2) proporcje masonry
        await ev("PF.navigate('/portfolio/rajd'); 'ok'")
        await wait_js("document.querySelectorAll('.mcell').length === 14")
        await asyncio.sleep(1.2)
        ratios = await ev(
            "[...document.querySelectorAll('.mcell img')].slice(0, 8).map(img => {"
            "  const r = img.getBoundingClientRect();"
            "  const nat = img.naturalWidth / img.naturalHeight;"
            "  const ren = r.width / r.height;"
            "  return Math.abs(nat - ren).toFixed(4);"
            "})"
        )
        print("roznice naturalny vs renderowany (0 = idealnie):", ratios)

        # 3) picker: filtr + grupy + strzalki
        await send("Page.navigate", {"url": BASE + "/admin"})
        await wait_js("document.querySelector('#login-form') !== null || document.querySelector('.admin-shell') !== null")
        if await ev("!!document.querySelector('#login-form')"):
            pw = os.environ.get("PF_ADMIN_PASS", "admin")
            await ev(f"(() => {{const f=document.querySelector('#login-form');"
                     f"document.querySelector('#a-pass').value={json.dumps(pw)};f.requestSubmit();}})()")
        await wait_js("document.querySelector('.admin-shell') !== null")
        await asyncio.sleep(0.6)
        await ev("document.querySelector('[data-sec=\"featured\"]').click()")
        await wait_js("document.querySelector('#feat-preview-grid .fcell') !== null")
        await asyncio.sleep(0.5)
        print("grupy albumow:", await ev("document.querySelectorAll('.feat-group-head').length"))
        print("wybrane (pasek):", await ev("document.querySelectorAll('#feat-selected .a-photo').length"))
        # filtr
        await ev("(() => {const i=document.querySelector('#feat-filter'); i.value='Kadr'; i.dispatchEvent(new Event('input'));})()")
        await asyncio.sleep(0.4)
        print("grupy po filtrze 'Kadr':", await ev("document.querySelectorAll('.feat-group-head').length"))
        await ev("(() => {const i=document.querySelector('#feat-filter'); i.value=''; i.dispatchEvent(new Event('input'));})()")
        await asyncio.sleep(0.4)
        # strzalka w prawo na pierwszym elemencie paska
        first_before = await ev("document.querySelector('#feat-selected .cover-tag').textContent")
        await ev("document.querySelector('#feat-selected [data-feat-mv][data-dir=\"1\"]').click()")
        await asyncio.sleep(0.4)
        first_after = await ev("document.querySelector('#feat-selected .cover-tag').textContent")
        print("strzalka: pierwszy przed:", first_before, "po:", first_after, "(kolejność powinna się zmienić)")
        # cofnij zmiane (strzalka w lewo na drugim elemencie)
        await ev("document.querySelectorAll('#feat-selected [data-feat-mv][data-dir=\"-1\"]')[1].click()")
        await asyncio.sleep(0.4)
        print("cofnieto:", await ev("document.querySelector('#feat-selected .cover-tag').textContent"))
        # +Dodaj album — nie klikamy (limit), sprawdzamy tylko obecnosc przyciskow
        print("przyciski Dodaj album:", await ev("document.querySelectorAll('[data-feat-add-album]').length"))
        # NIE zapisujemy — stan bez zmian


asyncio.run(main())

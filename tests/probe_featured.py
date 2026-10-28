"""Probe UI: zakladka Wyroznione — render, toggle, zapis, weryfikacja + przywrocenie."""
import asyncio
import base64
import json
import os
import time
from pathlib import Path

import httpx
import websockets

CDP_PORT = 9222
BASE = "http://127.0.0.1:8000"
OUT = Path(__file__).resolve().parent / "shots"
ORIG_IDS = [1, 2, 17, 18, 19, 20]


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
        await send("Page.navigate", {"url": BASE + "/admin"})
        await wait_js("document.querySelector('#login-form') !== null || document.querySelector('.admin-shell') !== null")
        if await ev("!!document.querySelector('#login-form')"):
            pw = os.environ.get("PF_ADMIN_PASS", "admin")
            await ev(f"(() => {{const f=document.querySelector('#login-form');"
                     f"document.querySelector('#a-pass').value={json.dumps(pw)};f.requestSubmit();}})()")
        await wait_js("document.querySelector('.admin-shell') !== null")
        await asyncio.sleep(0.8)

        # wejdz w Wyroznione
        await ev("document.querySelector('[data-sec=\"featured\"]').click()")
        await wait_js("document.querySelector('#feat-all .a-photo') !== null")
        n_all = await ev("document.querySelectorAll('#feat-all .a-photo').length")
        n_sel = await ev("document.querySelectorAll('#feat-selected .a-photo').length")
        print("wszystkie zdjecia w pickerze:", n_all, "| wybrane:", n_sel)

        # toggle: kliknij pierwsze niewybrane zdjecie w #feat-all (bez feat-sel)
        r = await ev(
            "(() => {const c=document.querySelector('#feat-all .a-photo:not(.feat-sel)');"
            "c.click(); return c.dataset.featPid;})()"
        )
        await asyncio.sleep(0.4)
        print("klikniete zdjecie id:", r, "| wybrane po toggle:", await ev("document.querySelectorAll('#feat-selected .a-photo').length"))
        await asyncio.sleep(0.3)
        shot = await send("Page.captureScreenshot", {"format": "jpeg", "quality": 85, "captureBeyondViewport": False})
        (OUT / "17-featured-admin.jpg").write_bytes(base64.b64decode(shot["result"]["data"]))
        print("shot: 17-featured-admin.jpg")

        # zapisz
        await ev("document.querySelector('#feat-save').click()")
        await asyncio.sleep(1.0)

        # weryfikacja przez API
        async with httpx.AsyncClient() as c:
            site = (await c.get(BASE + "/api/site")).json()
        ids = [p["id"] for p in site["featured"]]
        print("site featured po zapisie:", ids, "| ma byc 7 sztuk:", len(ids) == 7)

        # przywrocenie oryginalu przez API
        csrf_res = await ev(
            "fetch('/api/me', {credentials:'same-origin'}).then(r=>r.json()).then(j=>j.csrf)"
        )
        restored = await ev(
            f"fetch('/api/admin/featured', {{method:'POST', credentials:'same-origin',"
            f"headers: {{'Content-Type':'application/json','X-CSRF': arguments[0]}},"
            f"body: JSON.stringify({{ids: {json.dumps(ORIG_IDS)}}})}}).then(r=>r.ok)"
            .replace("arguments[0]", json.dumps(csrf_res))
        )
        print("przywrocono:", restored)
        async with httpx.AsyncClient() as c:
            site2 = (await c.get(BASE + "/api/site")).json()
        print("final featured:", [p["id"] for p in site2["featured"]])


asyncio.run(main())

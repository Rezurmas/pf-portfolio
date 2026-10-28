"""Probe: PRAWDZIWY klik myszy (Input.dispatchMouseEvent) na przycisk rozmiaru."""
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

        # znajdz przycisk "3:1" (panorama) pierwszej komorki — jego srodek
        coords = await ev(
            "(() => {const b=document.querySelector('#feat-preview-grid .fcell [data-feat-size][data-sz=\"full\"]');"
            "const r=b.getBoundingClientRect();"
            "return JSON.stringify({x: r.left + r.width/2, y: r.top + r.height/2, label: b.textContent});})()"
        )
        print("przycisk:", coords)
        cx = json.loads(coords)

        # prawdziwy klik
        await send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": cx["x"], "y": cx["y"], "button": "left", "clickCount": 1})
        await send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": cx["x"], "y": cx["y"], "button": "left", "clickCount": 1})
        await asyncio.sleep(0.6)

        cls0 = await ev("document.querySelector('#feat-preview-grid .fcell').className")
        print("klasa 1. komorki po kliku (ma byc full):", cls0)
        # zapis + sprawdzenie przez API
        await ev("document.querySelector('#feat-save').click()")
        await asyncio.sleep(1.0)
        async with httpx.AsyncClient() as c:
            site = (await c.get(BASE + "/api/site")).json()
        print("site feat_size[0]:", site["featured"][0].get("feat_size") if site["featured"] else None)

        # przywrocenie: rozmiary puste
        me = await ev("fetch('/api/me', {credentials:'same-origin'}).then(r=>r.json())")
        csrf = me.get("csrf", "") if isinstance(me, dict) else ""
        ids = await ev(
            "fetch('/api/admin/featured', {credentials:'same-origin',"
            f"headers: {{'X-CSRF': {json.dumps(csrf)}}}}}).then(r=>r.json())"
            ".then(j=>j.photos.filter(p=>p.featured).sort((a,b)=>a.feat_pos-b.feat_pos).map(p=>p.id))"
        )
        await ev(
            "fetch('/api/admin/featured', {method:'POST', credentials:'same-origin',"
            f"headers: {{'Content-Type':'application/json','X-CSRF':{json.dumps(csrf)}}},"
            f"body: JSON.stringify({{ids: {json.dumps(ids)}, sizes: {{}}}})}}).then(r=>r.ok)"
        )
        print("przywrocono puste rozmiary dla:", ids)


asyncio.run(main())

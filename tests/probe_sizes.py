"""Probe: podgląd sekcji wyroznionych + rozmiary + zapis."""
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

        # snapshot (ids + sizes) do przywrocenia
        me = await ev("fetch('/api/me', {credentials:'same-origin'}).then(r=>r.json())")
        csrf = me.get("csrf", "") if isinstance(me, dict) else ""
        snap = await ev(
            "(() => { const run = async () => {"
            "const me2 = await fetch('/api/me', {credentials:'same-origin'}).then(r=>r.json());"
            f"const j = await fetch('/api/admin/featured', {{credentials:'same-origin', headers: {{'X-CSRF': {json.dumps(csrf)}}}}}).then(r=>r.json());"
            "return j.photos.filter(p=>p.featured).sort((a,b)=>a.feat_pos-b.feat_pos).map(p=>({id: p.id, sz: p.feat_size||''}));"
            "}; return run(); })()"
        )
        print("snapshot:", snap)

        await ev("document.querySelector('[data-sec=\"featured\"]').click()")
        await wait_js("document.querySelector('#feat-preview-grid .fcell') !== null")
        await asyncio.sleep(0.4)
        cells = await ev("document.querySelectorAll('#feat-preview-grid .fcell').length")
        sizes = await ev(
            "[...document.querySelectorAll('#feat-preview-grid .fcell')].map(c=>c.className.replace('fcell','').trim())"
        )
        print("podglad — komorki:", cells, "| klasy:", sizes)

        # zmiana rozmiaru pierwszej komorki na full
        await ev("document.querySelector('#feat-preview-grid [data-feat-size][data-sz=\"full\"]').click()")
        await asyncio.sleep(0.4)
        cls0 = await ev("document.querySelector('#feat-preview-grid .fcell').className")
        print("po kliknieciu full na 1. komorce:", cls0)

        # zapis i weryfikacja przez /api/site
        await ev("document.querySelector('#feat-save').click()")
        await asyncio.sleep(1.0)
        async with httpx.AsyncClient() as c:
            site = (await c.get(BASE + "/api/site")).json()
        print("site featured feat_size:", [p.get("feat_size") for p in site["featured"]])

        shot = await send("Page.captureScreenshot", {"format": "jpeg", "quality": 85, "captureBeyondViewport": False})
        (OUT / "18-feat-preview.jpg").write_bytes(base64.b64decode(shot["result"]["data"]))
        print("shot: 18-feat-preview.jpg")

        # przywrocenie snapshotu
        ids = [p["id"] for p in snap]
        sizes_r = {str(p["id"]): p["sz"] for p in snap if p["sz"]}
        await ev(
            "fetch('/api/admin/featured', {method:'POST', credentials:'same-origin',"
            f"headers: {{'Content-Type':'application/json','X-CSRF':{json.dumps(csrf)}}},"
            f"body: JSON.stringify({{ids: {json.dumps(ids)}, sizes: {json.dumps(sizes_r)}}})}}).then(r=>r.ok)"
        )
        async with httpx.AsyncClient() as c:
            site2 = (await c.get(BASE + "/api/site")).json()
        print("przywrocono:", [(p["id"], p.get("feat_size")) for p in site2["featured"]])


asyncio.run(main())

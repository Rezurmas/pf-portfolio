"""Probe DnD: dragstart trzęsie, drop na pasek dodaje w miejscu."""
import asyncio
import json
import os
import time

import httpx
import websockets

CDP_PORT = 9222
BASE = "http://127.0.0.1:8000"
ORIG_IDS = None  # snapshot pobierany z API na starcie


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
        await wait_js("document.querySelector('#feat-all .a-photo') !== null")
        await asyncio.sleep(0.4)

        # snapshot aktualnego stanu (przywrocimy go po tescie — uzytkownik moze
        # miec wlasny wybor rownolegle); GET admina wymaga X-CSRF
        snap = await ev(
            "fetch('/api/me', {credentials:'same-origin'}).then(r=>r.json()).then(me=>"
            "fetch('/api/admin/featured', {credentials:'same-origin',"
            "headers: {'X-CSRF': me.csrf}})).then(r=>r.json())"
            ".then(j=>j.photos.filter(p=>p.featured).sort((a,b)=>a.feat_pos-b.feat_pos).map(p=>p.id))"
        )
        print("snapshot wyroznionych:", snap)

        # 1. dragstart na pierwszym niewybranym — ma sie zatrzasc
        r = await ev(
            "(() => {const c=document.querySelector('#feat-all .a-photo:not(.feat-sel)');"
            "const id=c.dataset.featPid;"
            "c.dispatchEvent(new DragEvent('dragstart', {bubbles:true, dataTransfer:null}));"
            "return JSON.stringify({id, shake: c.classList.contains('drag-shake')});})()"
        )
        print("dragstart:", r)

        # 2. drop na pasku (za pierwsza komorka, clientX na prawo od jej srodka)
        before = await ev("document.querySelectorAll('#feat-selected .a-photo').length")
        r2 = await ev(
            "(() => {const t=document.querySelector('#feat-selected .a-photo');"
            "const rect=t.getBoundingClientRect();"
            "const x=rect.left+rect.width*0.9;"
            "t.dispatchEvent(new DragEvent('drop', {bubbles:true, clientX:x}));"
            "return document.querySelectorAll('#feat-selected .a-photo').length;})()"
        )
        print("drop na pasek: przed:", before, "po:", r2)

        # 3. zapis i weryfikacja na /api/site
        await ev("document.querySelector('#feat-save').click()")
        await asyncio.sleep(1.0)
        async with httpx.AsyncClient() as c:
            site = (await c.get(BASE + "/api/site")).json()
        print("site featured:", [p["id"] for p in site["featured"]])

        # przywrocenie snapshotu
        me = await ev("fetch('/api/me', {credentials:'same-origin'}).then(r=>r.json())")
        csrf = me.get("csrf", "") if isinstance(me, dict) else ""
        await ev(
            "fetch('/api/admin/featured', {method:'POST', credentials:'same-origin',"
            f"headers: {{'Content-Type':'application/json','X-CSRF':{json.dumps(csrf)}}},"
            f"body: JSON.stringify({{ids: {json.dumps(snap)}}})}}).then(r=>r.ok)"
        )
        async with httpx.AsyncClient() as c:
            site2 = (await c.get(BASE + "/api/site")).json()
        print("przywrocono snapshot:", [p["id"] for p in site2["featured"]])


asyncio.run(main())

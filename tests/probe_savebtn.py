"""Probe: klik w wiersz albumu otwiera edytor; Zapisz wybor — stany szary/bialy."""
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

        # 1. albumy: klik w wiersz otwiera edytor
        await ev("document.querySelector('[data-sec=\"albums\"]').click()")
        await wait_js("document.querySelectorAll('#albums-list .a-row').length === 4")
        await ev("document.querySelector('#albums-list .a-row').click()")
        await wait_js("document.querySelector('#a-photo-grid') !== null")
        print("klik w wiersz -> edytor:", await ev("!!document.querySelector('#album-edit-form')"))

        # 2. wyroznione: stan przycisku
        await ev("document.querySelector('[data-sec=\"featured\"]').click()")
        await wait_js("document.querySelector('#feat-save') !== null")
        await asyncio.sleep(0.4)
        state0 = await ev(
            "JSON.stringify({cls: document.querySelector('#feat-save').className,"
            " txt: document.querySelector('#feat-save').textContent.trim()})"
        )
        print("po wejsciu:", state0)

        # zmiana (toggle) -> ma byc dirty/bialy
        await ev("document.querySelector('#feat-all .a-photo:not(.feat-sel)').click()")
        await asyncio.sleep(0.4)
        state1 = await ev(
            "JSON.stringify({cls: document.querySelector('#feat-save').className,"
            " txt: document.querySelector('#feat-save').textContent.trim()})"
        )
        print("po zmianie:", state1)

        # zapisz -> wraca do szarego
        await ev("document.querySelector('#feat-save').click()")
        await asyncio.sleep(1.0)
        state2 = await ev(
            "JSON.stringify({cls: document.querySelector('#feat-save').className,"
            " txt: document.querySelector('#feat-save').textContent.trim()})"
        )
        print("po zapisie:", state2)

        # przywrocenie stanu uzytkownika
        me = await ev("fetch('/api/me', {credentials:'same-origin'}).then(r=>r.json())")
        csrf = me.get("csrf", "") if isinstance(me, dict) else ""
        await ev(
            "fetch('/api/admin/featured', {method:'POST', credentials:'same-origin',"
            f"headers: {{'Content-Type':'application/json','X-CSRF':{json.dumps(csrf)}}},"
            "body: JSON.stringify({ids: [1,2,17,19,20,4,5]})}).then(r=>r.ok)"
        )
        print("przywrocono wybor uzytkownika")


asyncio.run(main())

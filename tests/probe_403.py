"""Debug: który request dostaje 403 po zalogowaniu (czy to cleanup wiadomości?)."""
import asyncio
import json
import os

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
        events = []

        async def send(method, params=None):
            nonlocal mid
            mid += 1
            await ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
            while True:
                msg = json.loads(await ws.recv())
                if msg.get("id") == mid:
                    return msg
                m = msg.get("method")
                if m == "Network.responseReceived" and msg["params"]["response"]["status"] >= 400:
                    events.append((msg["params"]["response"]["status"], msg["params"]["response"]["url"]))

        async def ev(expr):
            r = await send("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True})
            res = r.get("result", {})
            if res.get("exceptionDetails"):
                return "EXC: " + str(res["exceptionDetails"].get("exception", {}).get("description", ""))[:150]
            return res.get("result", {}).get("value")

        async def wait_js(cond, timeout=15):
            import time
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
        await send("Network.enable")
        await send("Page.navigate", {"url": BASE + "/admin"})
        await wait_js("document.querySelector('#login-form') !== null || document.querySelector('.admin-shell') !== null")
        if await ev("!!document.querySelector('#login-form')"):
            pw = os.environ.get("PF_ADMIN_PASS", "admin")
            await ev(f"(() => {{const f=document.querySelector('#login-form');"
                     f"document.querySelector('#a-pass').value={json.dumps(pw)};f.requestSubmit();}})()")
        await wait_js("document.querySelector('.admin-shell') !== null")
        await asyncio.sleep(0.6)
        # czysty cleanup z logowaniem statusow
        result = await ev(
            "fetch('/api/me', {credentials:'same-origin'}).then(r=>r.json()).then(async (m) => {"
            "  const list = await fetch('/api/admin/messages', {credentials:'same-origin'}).then(r=>r.json());"
            "  const out = [];"
            "  for (const msg of (list.messages || [])) {"
            "    if ((msg.name || '').includes('Test CDP')) {"
            "      const r = await fetch('/api/admin/messages/' + msg.id, {method:'DELETE', credentials:'same-origin', headers:{'X-CSRF': m.csrf}});"
            "      out.push(msg.id + ':' + r.status);"
            "    }"
            "  }"
            "  return out.join(',');"
            "})"
        )
        print("cleanup statusy:", result)
        print("403 requests:", events or "brak")


asyncio.run(main())

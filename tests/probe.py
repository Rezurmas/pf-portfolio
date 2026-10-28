"""Sonda: czemu login nie przechodzi. Uruchom: .venv/Scripts/python tests/probe.py"""
import asyncio
import json
import time

import httpx
import websockets

CDP_PORT = 9222
BASE = "http://127.0.0.1:8000"
events: list[str] = []


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
                m = msg.get("method")
                if m == "Runtime.exceptionThrown":
                    events.append("EXC: " + str(msg["params"]["exceptionDetails"].get("exception", {}).get("description"))[:180])
                if m == "Runtime.consoleAPICalled":
                    events.append("CONSOLE " + msg["params"].get("type", "") + ": "
                                  + " ".join(str(a.get("value", "")) for a in msg["params"]["args"])[:180])

        async def ev(expr):
            r = await send("Runtime.evaluate", {"expression": expr, "returnByValue": True, "awaitPromise": True})
            res = r.get("result", {}).get("result", {})
            if r.get("result", {}).get("exceptionDetails"):
                events.append("EVAL-EXC: " + r["result"]["exceptionDetails"].get("text", ""))
                return None
            return res.get("value")

        async def wait_js(cond, timeout=12):
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
        await send("Page.navigate", {"url": BASE + "/"})
        await wait_js("document.querySelector('.hero-title .l')")
        print("1. home ok")

        # przechwytujemy fetch
        await ev("window.__fl=[];const _f=window.fetch;window.fetch=(u,o)=>{window.__fl.push((o&&o.method||'GET')+' '+u);return _f(u,o);};'ok'")

        # SPA nawigacja do /admin
        r = await ev("PF.navigate('/admin'); 'ok'")
        print("2. navigate wywołany:", r)
        ok = await wait_js("document.querySelector('#login-form') !== null")
        print("3. login-form w DOM:", ok)
        state = await ev(
            "JSON.stringify({path: location.pathname, wipeClass: document.querySelector('#wipe').className,"
            " formCount: document.querySelectorAll('#login-form').length,"
            " viewLen: document.querySelector('#view').innerHTML.length,"
            " fl: window.__fl})"
        )
        print("4. stan:", state)

        # requestSubmit
        r = await ev(
            "(() => {const f=document.querySelector('#login-form');"
            "document.querySelector('#a-pass').value='admin';"
            "f.requestSubmit(); return 'submitted';})()"
        )
        print("5. requestSubmit:", r)
        await asyncio.sleep(2.5)
        state = await ev("JSON.stringify({path: location.pathname, fl: window.__fl, shell: !!document.querySelector('.admin-shell'), err: document.querySelector('#login-err')?.className})")
        print("6. po submicie:", state)

        print("events:")
        for e in events:
            print("  ", e)


asyncio.run(main())

"""Probe: grain statyczny + brak footer-word + zero bledow."""
import asyncio
import json
import time

import httpx
import websockets

CDP_PORT = 9222
BASE = "http://127.0.0.1:8000"
errors: list[str] = []


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
                    errors.append(str(msg["params"]["exceptionDetails"].get("text", "")))
                if m == "Runtime.consoleAPICalled" and msg["params"].get("type") == "error":
                    errors.append("console.error")

        async def ev(expr):
            r = await send("Runtime.evaluate", {"expression": expr, "returnByValue": True})
            return r.get("result", {}).get("result", {}).get("value")

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
        await send("Page.navigate", {"url": BASE + "/"})
        await wait_js("document.querySelector('.hero-title .l') && !document.querySelector('#preloader')")
        await asyncio.sleep(0.8)
        grain = await ev("getComputedStyle(document.querySelector('#grain')).animationName")
        word = await ev("document.querySelector('#footer-word') === null")
        footer = await ev("document.querySelector('#site-footer').hidden")
        print("grain animation:", repr(grain), "(ma byc 'none')")
        print("footer-word usuniety:", word)
        print("footer widoczny:", not footer)
        await asyncio.sleep(0.6)
        print("bledy konsoli:", len(errors))


asyncio.run(main())

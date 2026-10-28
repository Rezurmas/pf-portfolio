"""Sonda hero: czemu zdjęcie nie jest widoczne."""
import asyncio
import json

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
                return "EVAL_ERROR: " + res["exceptionDetails"].get("text", "") + " " + str(
                    res["exceptionDetails"].get("exception", {}).get("description", ""))[:200]
            return res.get("result", {}).get("value")

        async def wait_js(cond, timeout=15):
            import time
            t0 = time.time()
            while time.time() - t0 < timeout:
                v = await ev(cond)
                if v is True:
                    return True
                await asyncio.sleep(0.3)
            return False

        await send("Runtime.enable")
        await send("Page.enable")
        await send("Emulation.setDeviceMetricsOverride",
                   {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False})
        await send("Page.navigate", {"url": BASE + "/"})
        ok = await wait_js("document.querySelector('.hero-title .l') && !document.querySelector('#preloader')")
        print("hero gotowy:", ok)
        await asyncio.sleep(1.0)
        out = {}
        out["img"] = await ev(
            "(() => {const i=document.querySelector('.hero-media img');"
            "return {src: i&&i.getAttribute('src'), nw: i&&i.naturalWidth, nh: i&&i.naturalHeight,"
            "complete: i&&i.complete, rect: i&&i.getBoundingClientRect().toJSON()};})()"
        )
        out["hm"] = await ev(
            "(() => {const h=document.querySelector('.hero-media');const cs=getComputedStyle(h);"
            "return {rect: h.getBoundingClientRect().toJSON(), z: cs.zIndex, pos: cs.position, disp: cs.display};})()"
        )
        out["hero"] = await ev(
            "(() => {const h=document.querySelector('.hero');const cs=getComputedStyle(h);"
            "return {pos: cs.position, z: cs.zIndex, overflow: cs.overflow};})()"
        )
        out["cursor"] = await ev(
            "(() => {const d=document.querySelector('#cursor-dot'), r=document.querySelector('#cursor-ring');"
            "return {dotO: getComputedStyle(d).opacity, dotX: d.getBoundingClientRect().x,"
            "ringO: getComputedStyle(r).opacity, ringX: r.getBoundingClientRect().x};})()"
        )
        out["bodyBg"] = await ev("getComputedStyle(document.body).backgroundColor")
        print(json.dumps(out, ensure_ascii=False, indent=1))


asyncio.run(main())

"""Probe: stan sekcji about — clip, kolor, tlo."""
import asyncio
import json
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
            r = await send("Runtime.evaluate", {"expression": expr, "returnByValue": True})
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
        await send("Page.navigate", {"url": BASE + "/"})
        await wait_js("document.querySelector('.hero-title .l') && !document.querySelector('#preloader')")
        await asyncio.sleep(0.6)
        await ev("document.querySelector('#about').scrollIntoView()")
        await asyncio.sleep(1.6)
        out = await ev(
            "(() => {const s=document.querySelector('#about');const lead=document.querySelector('.about-lead');"
            "const p=document.querySelector('.about-lead p');"
            "const cs=(el,pr)=>el?getComputedStyle(el)[pr]:null;"
            "return JSON.stringify({"
            " secBg: cs(s,'backgroundColor'), secColor: cs(s,'color'),"
            " invVars: (()=>{const st=getComputedStyle(s);return [st.getPropertyValue('--bg').trim(), st.getPropertyValue('--fg').trim()];})(),"
            " leadIsIn: lead&&lead.classList.contains('is-in'),"
            " leadClip: cs(lead,'clipPath'),"
            " leadOpacity: cs(lead,'opacity'),"
            " pColor: cs(p,'color'), pVis: cs(p,'visibility'), pText: p?p.textContent.slice(0,40):null,"
            " leadRect: lead?lead.getBoundingClientRect().height:null,"
            " scrollY: scrollY"
            "});})()"
        )
        print(out)


asyncio.run(main())

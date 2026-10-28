"""Probe: B/W toggle w lightboxie ma pamiec (kolor trzyma sie po przejsciu na kolejne zdjecie)."""
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
                return "EXC: " + str(res["exceptionDetails"].get("exception", {}).get("description", ""))[:120]
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
        await send("Page.navigate", {"url": BASE + "/"})
        await wait_js("document.querySelector('.hero-title .l') && !document.querySelector('#preloader')")

        # do albumu "Rajd" (14 zdjec) przez SPA
        await ev("PF.navigate('/portfolio/rajd'); 'ok'")
        await wait_js("document.querySelectorAll('.mcell').length === 14")
        print("album rajd: 14 komorek")

        # otworz lightbox na 1. zdjeciu
        await ev("document.querySelector('.mcell').click()")
        await wait_js("document.querySelector('#lightbox').classList.contains('open')")
        print("lightbox otwarty, color na starcie:", await ev("document.querySelector('#lb-img').classList.contains('color')"))

        # wlacz kolor
        await ev("document.querySelector('#lb-bw').click()")
        print("po togglu: color =", await ev("document.querySelector('#lb-img').classList.contains('color')"),
              "| przycisk .on =", await ev("document.querySelector('#lb-bw').classList.contains('on')"))

        # przejdz na kolejne zdjecie
        await ev("document.querySelector('#lb-next').click()")
        await asyncio.sleep(0.8)
        print("po next: licznik =", await ev("document.querySelector('#lb-count').textContent"),
              "| color nadal =", await ev("document.querySelector('#lb-img').classList.contains('color')"))

        # jeszcze raz next i sprawdz
        await ev("document.querySelector('#lb-next').click()")
        await asyncio.sleep(0.8)
        print("po 2x next: licznik =", await ev("document.querySelector('#lb-count').textContent"),
              "| color nadal =", await ev("document.querySelector('#lb-img').classList.contains('color')"))

        # wylacz kolor i next — ma zostac BW
        await ev("document.querySelector('#lb-bw').click()")
        await ev("document.querySelector('#lb-next').click()")
        await asyncio.sleep(0.8)
        print("po wylaczeniu + next: color =", await ev("document.querySelector('#lb-img').classList.contains('color')"))

        # zamknij i otworz ponownie — ma startowac BW (reset)
        await ev("document.querySelector('#lb-close').click()")
        await asyncio.sleep(0.4)
        await ev("document.querySelector('.mcell').click()")
        await asyncio.sleep(0.6)
        print("po ponownym otwarciu: color =", await ev("document.querySelector('#lb-img').classList.contains('color')"),
              "| przycisk .on =", await ev("document.querySelector('#lb-bw').classList.contains('on')"))


asyncio.run(main())

"""Debug strzałek w pasku wyróżnionych — czysty plik, zero escaping-masakry."""
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

        async def ev(expr):
            nonlocal mid
            mid += 1
            await ws.send(json.dumps({"id": mid, "method": "Runtime.evaluate",
                                      "params": {"expression": expr, "returnByValue": True, "awaitPromise": True}}))
            while True:
                m = json.loads(await ws.recv())
                if m.get("id") == mid:
                    res = m.get("result", {})
                    if res.get("exceptionDetails"):
                        return "EXC: " + str(res["exceptionDetails"].get("exception", {}).get("description", ""))[:250]
                    return res.get("result", {}).get("value")

        # 1. wlasny handler z licznikiem + klik
        out = await ev(
            "(() => {"
            "const s = document.querySelector('#feat-selected');"
            "window.__mine = 0;"
            "s.addEventListener('click', () => { window.__mine++; });"
            "const b = document.querySelector('#feat-selected [data-feat-mv][data-dir=\"1\"]');"
            "b.click();"
            "return 'moj handler: ' + window.__mine + ', target = ' + b.tagName;"
            "})()"
        )
        print(out)
        print("mvDebug (handler aplikacji):", await ev("window.__mvDebug"))
        print("kolejnosc:", await ev(
            "[...document.querySelectorAll('#feat-selected .a-photo')].map(x=>x.dataset.featPid).join(',')"
        ))
        # 2. czy handler aplikacji zyje? klik w puste miejsce paska (nie przycisk)
        await ev("document.querySelector('#feat-selected').click()")
        print("mvDebug po kliku w pasek:", await ev("window.__mvDebug"))


asyncio.run(main())

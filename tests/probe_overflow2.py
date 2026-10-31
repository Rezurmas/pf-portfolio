"""Identyfikacja overflowera 562px na home — pelny lancuch rodzicow."""
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
                        return "EXC: " + str(res["exceptionDetails"].get("exception", {}).get("description", ""))[:150]
                    return res.get("result", {}).get("value")

        await ev("PF.navigate('/'); 'ok'")
        await asyncio.sleep(2.5)
        report = await ev(
            "(() => {"
            "const w = document.documentElement.clientWidth;"
            "const out = [];"
            "document.querySelectorAll('body *').forEach(el => {"
            "  const r = el.getBoundingClientRect();"
            "  const pos = getComputedStyle(el).position;"
            "  if (r.right > w + 2 && pos !== 'fixed' && pos !== 'absolute' && !el.closest('.marquee')) {"
            "    let desc = el.tagName;"
            "    if (el.id) desc += '#' + el.id;"
            "    if (typeof el.className === 'string' && el.className) desc += '.' + el.className.split(' ').slice(0,2).join('.');"
            "    let par = el.parentElement;"
            "    const chain = [];"
            "    for (let i = 0; par && i < 4; i++) {"
            "      let p = par.tagName;"
            "      if (par.id) p += '#' + par.id;"
            "      if (typeof par.className === 'string' && par.className) p += '.' + par.className.split(' ').slice(0,2).join('.');"
            "      chain.push(p);"
            "      par = par.parentElement;"
            "    }"
            "    desc += ' [r=' + Math.round(r.right) + ' w=' + Math.round(r.width) + '] rodziec: ' + chain.join(' > ');"
            "    out.push(desc);"
            "  }"
            "});"
            "return out.slice(0, 12).join('\\n');"
            "})()"
        )
        print(report or "brak overflow (home)")
        print("scrollWidth:", await ev("document.documentElement.scrollWidth"))


asyncio.run(main())

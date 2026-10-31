"""Znajdz dokladnie element, ktory rozciaga strone na mobile (scrollWidth 462 vs 390)."""
import asyncio
import json

import httpx
import websockets

CDP_PORT = 9222


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

        report = await ev(
            "(() => {"
            "const w = document.documentElement.clientWidth;"
            "const out = [];"
            "document.querySelectorAll('*').forEach(el => {"
            "  const r = el.getBoundingClientRect();"
            "  if (r.right > w + 2 && !el.closest('.marquee') && !el.closest('#wipe') && !el.closest('#preloader')) {"
            "    let desc = el.tagName;"
            "    if (el.id) desc += '#' + el.id;"
            "    if (typeof el.className === 'string' && el.className) desc += '.' + el.className.split(' ').slice(0,2).join('.');"
            "    desc += ' [l=' + Math.round(r.left) + ' r=' + Math.round(r.right) + ' w=' + Math.round(r.width) + ']';"
            "    out.push(desc);"
            "  }"
            "});"
            "return out.slice(0, 15).join('\\n');"
            "})()"
        )
        print("elementy wystajace poza viewport (bez marquee):")
        print(report or "brak")


asyncio.run(main())

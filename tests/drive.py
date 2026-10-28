"""
Sterownik CDP — weryfikacja strony PF w headless Chrome.
Uruchom: .venv/Scripts/python tests/drive.py
"""
import asyncio
import base64
import json
import os
import sys
import time
from pathlib import Path

import httpx
import websockets

CDP_PORT = 9222
BASE = "http://127.0.0.1:8000"
OUT = Path(__file__).resolve().parent / "shots"
OUT.mkdir(exist_ok=True)

errors: list[str] = []
log_lines: list[str] = []


async def main() -> None:
    async with httpx.AsyncClient() as c:
        try:
            pages = (await c.get(f"http://127.0.0.1:{CDP_PORT}/json/list")).json()
        except Exception:
            print("FATAL: brak chromu na porcie", CDP_PORT)
            return
    page = next((p for p in pages if p["type"] == "page"), None)
    if page is None:
        async with httpx.AsyncClient() as c:
            page = (await c.put(f"http://127.0.0.1:{CDP_PORT}/json/new?{BASE}/")).json()
    ws_url = page["webSocketDebuggerUrl"]

    async with websockets.connect(ws_url, max_size=2**28) as ws:
        mid = 0

        async def send(method, params=None):
            nonlocal mid
            mid += 1
            await ws.send(json.dumps({"id": mid, "method": method, "params": params or {}}))
            while True:
                msg = json.loads(await ws.recv())
                if msg.get("id") == mid:
                    return msg
                _note_event(msg)

        def _note_event(msg):
            m = msg.get("method")
            if m == "Runtime.exceptionThrown":
                d = msg["params"]["exceptionDetails"]
                errors.append((d.get("exception", {}).get("description") or d.get("text", ""))[:220])
            elif m == "Log.entryAdded":
                e = msg["params"]["entry"]
                log_lines.append(f"{e.get('level')}: {(e.get('text') or '')[:160]}")
                if e.get("level") in ("error", "warning"):
                    errors.append(f"log:{e.get('text','')[:160]}")
            elif m == "Runtime.consoleAPICalled" and msg["params"].get("type") == "error":
                args = [a.get("value") or a.get("description") for a in msg["params"]["args"]]
                errors.append("console.error: " + "; ".join(str(a)[:140] for a in args))

        async def ev(expr, await_promise=True):
            r = await send(
                "Runtime.evaluate",
                {"expression": expr, "returnByValue": True, "awaitPromise": await_promise},
            )
            res = r.get("result", {})
            if res.get("exceptionDetails"):
                errors.append("eval: " + res["exceptionDetails"].get("text", "")[:200])
                return None
            rr = res.get("result", {})
            if rr.get("subtype") == "error":
                return None
            return rr.get("value")

        async def wait_js(cond, timeout=14, label=""):
            t0 = time.time()
            while time.time() - t0 < timeout:
                try:
                    if await ev(cond):
                        return True
                except Exception:
                    pass
                await asyncio.sleep(0.25)
            print(f"  TIMEOUT czekam na: {label}")
            return False

        async def shot(name, w=1440, h=900, mobile=False):
            await send(
                "Emulation.setDeviceMetricsOverride",
                {"width": w, "height": h, "deviceScaleFactor": 1, "mobile": mobile},
            )
            await asyncio.sleep(0.15)
            r = await send(
                "Page.captureScreenshot", {"format": "jpeg", "quality": 82, "captureBeyondViewport": False}
            )
            data = r.get("result", {}).get("data")
            if data:
                (OUT / name).write_bytes(base64.b64decode(data))
                print(f"  shot: {name}")
            else:
                print(f"  shot FAIL: {name}")

        print("== start ==")
        await send("Runtime.enable")
        await send("Log.enable")
        await send("Page.enable")

        await send("Page.navigate", {"url": BASE + "/"})
        ok = await wait_js(
            "document.querySelector('.hero-title .l') && !document.querySelector('#preloader')",
            label="hero po preloaderze",
        )
        print("home załadowany:", ok)
        checks = await ev(
            "(() => ({"
            " title: document.querySelector('.hero-title')?.innerText,"
            " letters: document.querySelectorAll('.hero-title .l').length,"
            " navLinks: document.querySelectorAll('.nav-links a').length,"
            " albumRows: document.querySelectorAll('.album-row').length,"
            " stats: [...document.querySelectorAll('.stat .num')].map(e=>e.textContent),"
            " grain: !!document.querySelector('#grain'),"
            " footerHidden: document.querySelector('#site-footer').hidden,"
            " marquee: !!document.querySelector('.marquee-track')"
            " }))()"
        )
        print(json.dumps(checks, ensure_ascii=False, indent=1))
        await asyncio.sleep(1.2)
        await shot("01-home.png".replace("png", "jpg"))

        # portfolio
        await ev("document.querySelector('a[href=\"/portfolio\"]').click()")
        await wait_js("document.querySelectorAll('.album-row').length === 4", label="4 albumy")
        rows = await ev("document.querySelectorAll('.album-row').length")
        print("portfolio rows:", rows)
        await asyncio.sleep(1.0)
        await shot("02-portfolio.jpg")

        # album
        await ev("document.querySelector('.album-row').click()")
        await wait_js("document.querySelectorAll('.mcell').length === 2", label="album stal i cegła")
        cells = await ev("document.querySelectorAll('.mcell').length")
        print("album cells:", cells)
        await asyncio.sleep(1.0)
        await shot("03-album.jpg")

        # lightbox
        await ev("document.querySelector('.mcell').click()")
        await wait_js(
            "document.querySelector('#lightbox').classList.contains('open')"
            " && document.querySelector('#lb-img').naturalWidth > 0",
            label="lightbox z obrazem",
        )
        lb = await ev(
            "(() => ({open: document.querySelector('#lightbox').classList.contains('open'),"
            " count: document.querySelector('#lb-count').textContent,"
            " w: document.querySelector('#lb-img').naturalWidth}))()"
        )
        print("lightbox:", json.dumps(lb))
        await asyncio.sleep(0.9)
        await shot("04-lightbox.jpg")
        await ev("document.querySelector('#lb-close').click()")

        # blog
        await ev("document.querySelector('a[href=\"/blog\"]').click()")
        await wait_js("document.querySelectorAll('.post-row').length === 3", label="3 wpisy")
        print("blog rows:", await ev("document.querySelectorAll('.post-row').length"))
        await asyncio.sleep(0.8)
        await shot("05-blog.jpg")

        # post
        await ev("document.querySelector('.post-row').click()")
        await wait_js("document.querySelector('.prose') !== null", label="treść wpisu")
        print("prose len:", await ev("document.querySelector('.prose').textContent.length"))
        await asyncio.sleep(0.8)
        await shot("06-post.jpg")

        # kontakt + wysyłka
        await ev("document.querySelector('a[href=\"/kontakt\"]').click()")
        await wait_js("document.querySelector('#contact-form') !== null", label="formularz")
        await ev(
            "(() => {const f=document.querySelector('#contact-form');"
            "f.elements.name.value='Test CDP';f.elements.email.value='test@cdp.pl';"
            "f.elements.message.value='Wiadomość testowa z weryfikacji.';f.requestSubmit();})()"
        )
        await wait_js(
            "document.querySelector('#form-success').classList.contains('show')", label="sukces formularza"
        )
        print("formularz: sukces")
        await asyncio.sleep(0.6)
        await shot("07-kontakt.jpg")

        # admin login (lub panel, jeśli sesja już istnieje)
        PW = os.environ.get("PF_ADMIN_PASS", "admin")
        await ev("document.querySelector('a[href=\"/admin\"]').click()")
        await wait_js(
            "document.querySelector('#login-form') !== null || document.querySelector('.admin-shell') !== null",
            label="admin (login lub panel)",
        )
        is_login = await ev("!!document.querySelector('#login-form')")
        if is_login:
            await asyncio.sleep(0.5)
            await shot("08-admin-login.jpg")
            await ev(
                f"(() => {{const f=document.querySelector('#login-form');"
                f"document.querySelector('#a-pass').value={json.dumps(PW)};f.requestSubmit();}})()"
            )
        ok_panel = await wait_js("document.querySelector('.admin-shell') !== null", label="panel po zalogowaniu")
        if ok_panel:
            cards = await ev("document.querySelectorAll('.a-card').length")
            print("panel: karty statystyk:", cards)
            await asyncio.sleep(0.8)
            await shot("09-admin-dash.jpg")

            # albumy w panelu
            await ev("document.querySelector('[data-sec=\"albums\"]').click()")
            await wait_js("document.querySelectorAll('#albums-list .a-row').length === 4", label="lista albumów w panelu")
            print("panel albumy rows:", await ev("document.querySelectorAll('#albums-list .a-row').length"))
            await asyncio.sleep(0.6)
            await shot("10-admin-albums.jpg")

            # otwórz edytor albumu
            await ev("document.querySelector('[data-open-album]').click()")
            await wait_js("document.querySelector('#a-photo-grid .a-photo') !== null", label="edytor albumu ze zdjęciami")
            print("panel edytor zdjęć:", await ev("document.querySelectorAll('#a-photo-grid .a-photo').length"))
            await asyncio.sleep(0.8)
            await shot("11-admin-album-editor.jpg")
        else:
            print("ADMIN SKIP: logowanie nieudane (ustaw PF_ADMIN_PASS, jesli haslo sie zmienilo)")

        # mobile
        await send(
            "Emulation.setDeviceMetricsOverride",
            {"width": 390, "height": 844, "deviceScaleFactor": 1, "mobile": True},
        )
        await send("Page.navigate", {"url": BASE + "/"})
        await wait_js("document.querySelector('.hero') !== null", label="mobile home (hero)")
        await asyncio.sleep(2.2)
        await shot("12-mobile-home.jpg", w=390, h=844, mobile=True)

        # search overlay
        await send("Emulation.setDeviceMetricsOverride",
                   {"width": 1440, "height": 900, "deviceScaleFactor": 1, "mobile": False})
        await send("Page.navigate", {"url": BASE + "/"})
        await wait_js("document.querySelector('.hero') !== null", label="home ponownie")
        await asyncio.sleep(2.0)
        await ev("document.querySelector('#nav-search').click()")
        await wait_js("document.querySelector('#search-overlay').classList.contains('open')", label="search open")
        await ev(
            "(() => {const i=document.querySelector('#search-input');"
            "i.value='rajd';i.dispatchEvent(new Event('input'));})()"
        )
        await wait_js("document.querySelectorAll('#search-results .sr-item').length >= 2", label="wyniki search")
        print("search results:", await ev("document.querySelectorAll('#search-results .sr-item').length"))
        await asyncio.sleep(0.7)
        await shot("13-search.jpg")

        print("== koniec ==")
        print("błędy konsoli/exceptions:", len(errors))
        for e in errors[:12]:
            print("  !", e)
        print("log lines:", len(log_lines))
        for l in log_lines[:12]:
            print("  L", l)


if __name__ == "__main__":
    asyncio.run(main())

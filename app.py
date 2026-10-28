"""
PF — portfolio fotograficzne. Backend.
FastAPI + SQLite (WAL) + Pillow. Zero zewnętrznych usług.

Struktura katalogów:
    app.py            — ten plik (API + serwer)
    public/           — frontend (index.html, css/, js/)
    data/site.db      — baza
    data/photos/      — oryginały zdjęć (per album)
    data/thumbs/      — miniatury do siatki (max 900px)
    data/large/       — wersje do lightboxa (max 2000px)
    data/secret.key   — sekret sesji

Uruchomienie:  .venv/Scripts/python -m uvicorn app:app --host 0.0.0.0 --port 8000
Pierwsze logowanie do panelu: hasło "admin" (zmień w Ustawieniach).
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import time
import unicodedata
import uuid
from collections import defaultdict
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from PIL import Image, ImageOps


class NoCacheStaticFiles(StaticFiles):
    """Pliki frontendu bez cache — zmiany widoczne od razu (strona w aktywnym rozwoju)."""

    async def get_response(self, path: str, scope):
        resp = await super().get_response(path, scope)
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return resp

# ------------------------------------------------------------------ paths --
BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
PHOTOS = DATA / "photos"
THUMBS = DATA / "thumbs"
LARGE = DATA / "large"
DB_PATH = DATA / "site.db"
SECRET_PATH = DATA / "secret.key"
PUBLIC = BASE / "public"

for d in (DATA, PHOTOS, THUMBS, LARGE):
    d.mkdir(parents=True, exist_ok=True)

ALLOWED_EXT = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
THUMB_SIZE = 900
LARGE_SIZE = 2000
SESSION_COOKIE = "pf_session"
SESSION_DAYS = 7

app = FastAPI(title="PF")

# ---------------------------------------------------------------- secret --
def get_secret() -> bytes:
    if not SECRET_PATH.exists():
        SECRET_PATH.write_bytes(secrets.token_bytes(32))
    return SECRET_PATH.read_bytes()


# ------------------------------------------------------------------ auth --
def hash_password(password: str, salt: str) -> str:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000).hex()


def make_token(csrf: str) -> str:
    payload = {"exp": int(time.time()) + SESSION_DAYS * 86400, "csrf": csrf}
    raw = json.dumps(payload).encode()
    sig = hmac.new(get_secret(), raw, hashlib.sha256).hexdigest()
    return raw.hex() + "." + sig


def check_token(token: str | None) -> dict | None:
    if not token:
        return None
    try:
        raw_hex, sig = token.split(".", 1)
        raw = bytes.fromhex(raw_hex)
        if not hmac.compare_digest(hmac.new(get_secret(), raw, hashlib.sha256).hexdigest(), sig):
            return None
        payload = json.loads(raw)
        if payload.get("exp", 0) < time.time():
            return None
        return payload
    except Exception:
        return None


def get_session(request: Request) -> dict | None:
    return check_token(request.cookies.get(SESSION_COOKIE))


def csrf_ok(request: Request, session: dict | None) -> bool:
    if not session:
        return False
    header = request.headers.get("x-csrf", "")
    return bool(header) and hmac.compare_digest(header, session.get("csrf", ""))


def require_admin(request: Request):
    session = get_session(request)
    if not session:
        raise HTTPException(status_code=401, detail="Zaloguj się")
    if not csrf_ok(request, session):
        raise HTTPException(status_code=403, detail="Nieprawidłowy CSRF")
    return session


# ------------------------------------------------------------ rate limit --
_RATE: dict[str, list[float]] = defaultdict(list)
_RATE_MAX = {"login": 8, "contact": 5}
_RATE_WINDOW = 900  # 15 min


def rate_check(request: Request, kind: str) -> None:
    ip = request.client.host if request.client else "?"
    now = time.time()
    hits = [t for t in _RATE[kind + ":" + ip] if now - t < _RATE_WINDOW]
    _RATE[kind + ":" + ip] = hits
    if len(hits) >= _RATE_MAX[kind]:
        raise HTTPException(status_code=429, detail="Za dużo prób. Spróbuj później.")
    _RATE[kind + ":" + ip].append(now)


# -------------------------------------------------------------------- db --
def db() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def init_db() -> None:
    conn = db()
    conn.execute("PRAGMA journal_mode = WAL")
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS albums (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            description TEXT DEFAULT '',
            cover_id INTEGER REFERENCES photos(id) ON DELETE SET NULL,
            position INTEGER DEFAULT 0,
            featured INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS photos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            album_id INTEGER NOT NULL REFERENCES albums(id) ON DELETE CASCADE,
            filename TEXT NOT NULL,
            title TEXT DEFAULT '',
            description TEXT DEFAULT '',
            position INTEGER DEFAULT 0,
            taken_at TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS posts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            slug TEXT NOT NULL UNIQUE,
            excerpt TEXT DEFAULT '',
            content TEXT DEFAULT '',
            tags TEXT DEFAULT '',
            cover_id INTEGER REFERENCES photos(id) ON DELETE SET NULL,
            published INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now','localtime')),
            updated_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT DEFAULT '',
            email TEXT DEFAULT '',
            message TEXT DEFAULT '',
            read INTEGER DEFAULT 0,
            created_at TEXT DEFAULT (datetime('now','localtime'))
        );
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT DEFAULT ''
        );
        """
    )
    defaults = {
        "site_title": "Dawid — Fotografia",
        "tagline": "Światło. Kadr. Czerń i biel.",
        "about_title": "O mnie",
        "about_text": (
            "Cześć. Jestem Dawid i fotografuję rzeczy, które inni mijają bez zatrzymania — "
            "światło na cegle, kurz na desce rozdzielczej, cień w lesie.\n\n"
            "Ten serwis to mój dom dla kadrów: albumy, notatki z plenerów i kontakt."
        ),
        "contact_email": "kontakt@dawid.foto",
        "contact_phone": "",
        "contact_instagram": "",
        "footer_text": "Wszystkie zdjęcia na tej stronie są mojego autorstwa.",
        "hero_photo_id": "",
        "admin_password_hash": "",
        "admin_password_salt": "",
        "password_changed": "0",
    }
    for key, value in defaults.items():
        conn.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))
    # migracja: kolumny wyróżnień zdjęć (sekcja "Wybrane prace")
    photo_cols = [r["name"] for r in conn.execute("PRAGMA table_info(photos)").fetchall()]
    if "featured" not in photo_cols:
        conn.execute("ALTER TABLE photos ADD COLUMN featured INTEGER DEFAULT 0")
    if "feat_pos" not in photo_cols:
        conn.execute("ALTER TABLE photos ADD COLUMN feat_pos INTEGER DEFAULT 0")
    if "feat_size" not in photo_cols:
        conn.execute("ALTER TABLE photos ADD COLUMN feat_size TEXT DEFAULT ''")
    if "tw" not in photo_cols:
        conn.execute("ALTER TABLE photos ADD COLUMN tw INTEGER DEFAULT 0")
    if "th" not in photo_cols:
        conn.execute("ALTER TABLE photos ADD COLUMN th INTEGER DEFAULT 0")
    conn.commit()
    # backfill wymiarów miniatur (CLS: atrybuty width/height w galerii)
    for r in conn.execute("SELECT id, album_id, filename FROM photos WHERE tw = 0 OR th = 0").fetchall():
        tp = THUMBS / str(r["album_id"]) / r["filename"]
        if tp.exists():
            try:
                with Image.open(tp) as im:
                    w, h = im.size
                conn.execute("UPDATE photos SET tw = ?, th = ? WHERE id = ?", (w, h, r["id"]))
            except Exception:
                pass
    conn.commit()
    # jednorazowe wypełnienie: jeśli nic nie wyróżnione, weź pierwsze zdjęcia
    # z wyróżnionych albumów (kolejność: albumy → zdjęcia)
    n_feat = conn.execute("SELECT COUNT(*) FROM photos WHERE featured = 1").fetchone()[0]
    if n_feat == 0:
        rows = conn.execute(
            "SELECT p.id FROM photos p JOIN albums a ON a.id = p.album_id "
            "WHERE a.featured = 1 ORDER BY a.position, p.position, p.id LIMIT 6"
        ).fetchall()
        for i, r in enumerate(rows):
            conn.execute(
                "UPDATE photos SET featured = 1, feat_pos = ? WHERE id = ?", (i, r["id"])
            )
        conn.commit()
    conn.commit()
    conn.close()


def get_settings() -> dict:
    conn = db()
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    conn.close()
    return {r["key"]: r["value"] for r in rows}


def set_setting(key: str, value: str) -> None:
    conn = db()
    conn.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
    conn.commit()
    conn.close()


def verify_password(password: str) -> bool:
    s = get_settings()
    salt = s.get("admin_password_salt", "")
    stored = s.get("admin_password_hash", "")
    if not salt or not stored:
        return password == "admin"
    return hmac.compare_digest(hash_password(password, salt), stored)


# -------------------------------------------------------------- helpers --
_PL = str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ")


def slugify(text: str) -> str:
    text = text.translate(_PL)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return text or "pozycja"


def unique_slug(title: str, table: str) -> str:
    conn = db()
    base = slugify(title)
    slug, n = base, 2
    while conn.execute(f"SELECT 1 FROM {table} WHERE slug = ?", (slug,)).fetchone():
        slug = f"{base}-{n}"
        n += 1
    conn.close()
    return slug


def next_position(conn: sqlite3.Connection, table: str, where: str, args: tuple) -> int:
    row = conn.execute(
        f"SELECT COALESCE(MAX(position), -1) + 1 AS n FROM {table} WHERE {where}", args
    ).fetchone()
    return row["n"]


def photo_paths(photo: sqlite3.Row | dict) -> dict:
    album_id, filename = photo["album_id"], photo["filename"]
    orig_file = PHOTOS / str(album_id) / filename
    base = f"/{album_id}/{filename}"
    webp_thumb = (THUMBS / str(album_id) / (filename + ".webp")).exists()
    webp_large = (LARGE / str(album_id) / (filename + ".webp")).exists()
    return {
        "original": "/media" + base,
        "large": "/large" + base,
        "thumb": "/thumbs" + base,
        "large_webp": "/large" + base + ".webp" if webp_large else "/large" + base,
        "thumb_webp": "/thumbs" + base + ".webp" if webp_thumb else "/thumbs" + base,
        "tw": photo.get("tw") or 0,
        "th": photo.get("th") or 0,
        # download: oryginał, jeśli istnieje; w lekkiej paczce (bez oryginałów) — wersja large
        "download": "/media" + base if orig_file.exists()
        else "/large" + base,
    }


def photo_dict(p: sqlite3.Row) -> dict:
    d = dict(p)
    d.update(photo_paths(d))
    return d


def cover_of(conn: sqlite3.Connection, album_id: int | None) -> dict | None:
    if not album_id:
        return None
    album = conn.execute("SELECT * FROM albums WHERE id = ?", (album_id,)).fetchone()
    if not album:
        return None
    if album["cover_id"]:
        p = conn.execute("SELECT * FROM photos WHERE id = ?", (album["cover_id"],)).fetchone()
        if p:
            return photo_dict(p)
    p = conn.execute(
        "SELECT * FROM photos WHERE album_id = ? ORDER BY position, id LIMIT 1", (album_id,)
    ).fetchone()
    return photo_dict(p) if p else None


def photo_cover(conn: sqlite3.Connection, photo_id: int | None) -> dict | None:
    """Okładka wpisu: zdjęcie po id."""
    if not photo_id:
        return None
    p = conn.execute("SELECT * FROM photos WHERE id = ?", (photo_id,)).fetchone()
    return photo_dict(p) if p else None


def refresh_cover(conn: sqlite3.Connection, album_id: int) -> None:
    p = conn.execute(
        "SELECT id FROM photos WHERE album_id = ? ORDER BY position, id LIMIT 1", (album_id,)
    ).fetchone()
    conn.execute("UPDATE albums SET cover_id = ? WHERE id = ?", (p["id"] if p else None, album_id))


def read_exif_date(path: Path) -> str:
    try:
        img = Image.open(path)
        exif = img.getexif()
        for tag in (36867, 36868, 306):  # DateTimeOriginal, DateTimeDigitized, DateTime
            v = exif.get(tag)
            if v:
                v = str(v).strip()
                if re.match(r"\d{4}:\d{2}:\d{2}", v):
                    return v[:10].replace(":", "-")
    except Exception:
        pass
    return ""


def save_upload(album_id: int, file: UploadFile) -> int | None:
    """Zapis pliku + miniatura + wersja large. Zwraca id zdjęcia lub None."""
    raw = file.file.read()
    if not raw or len(raw) > 40 * 1024 * 1024:
        return None
    ext = Path(file.filename or "").suffix.lower()
    if ext not in ALLOWED_EXT:
        return None
    # magic bytes — nie ufamy rozszerzeniu
    sigs = {
        b"\xff\xd8\xff": ".jpg",
        b"\x89PNG": ".png",
        b"GIF87a": ".gif",
        b"GIF89a": ".gif",
        b"RIFF": ".webp" if raw[8:12] == b"WEBP" else "",
    }
    ok = False
    for sig, ext_out in sigs.items():
        if raw.startswith(sig):
            ok = bool(ext_out)
            if ext_out and ext_out != ext:
                ext = ext_out
            break
    if not ok:
        return None

    name = uuid.uuid4().hex + ext
    album_dir = PHOTOS / str(album_id)
    thumb_dir = THUMBS / str(album_id)
    large_dir = LARGE / str(album_id)
    album_dir.mkdir(parents=True, exist_ok=True)
    thumb_dir.mkdir(parents=True, exist_ok=True)
    large_dir.mkdir(parents=True, exist_ok=True)
    dest = album_dir / name
    dest.write_bytes(raw)

    try:
        img = Image.open(dest)
        img = ImageOps.exif_transpose(img)
        taken_at = read_exif_date(dest)
        if img.mode not in ("RGB", "L"):
            img = img.convert("RGB")
        img.thumbnail((THUMB_SIZE, THUMB_SIZE))
        tw, th = img.size
        img.save(thumb_dir / name, "JPEG", quality=85)
        img.save(thumb_dir / (name + ".webp"), "WEBP", quality=82)
        img2 = Image.open(dest)
        img2 = ImageOps.exif_transpose(img2)
        if img2.mode not in ("RGB", "L"):
            img2 = img2.convert("RGB")
        img2.thumbnail((LARGE_SIZE, LARGE_SIZE))
        img2.save(large_dir / name, "JPEG", quality=90)
        img2.save(large_dir / (name + ".webp"), "WEBP", quality=88)
    except Exception:
        for p in (dest, thumb_dir / name, large_dir / name,
                  thumb_dir / (name + ".webp"), large_dir / (name + ".webp")):
            p.unlink(missing_ok=True)
        return None

    conn = db()
    pos = next_position(conn, "photos", "album_id = ?", (album_id,))
    cur = conn.execute(
        "INSERT INTO photos (album_id, filename, position, taken_at, tw, th) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (album_id, name, pos, taken_at, tw, th),
    )
    if not conn.execute("SELECT cover_id FROM albums WHERE id = ?", (album_id,)).fetchone()[
        "cover_id"
    ]:
        conn.execute("UPDATE albums SET cover_id = ? WHERE id = ?", (cur.lastrowid, album_id))
    conn.commit()
    conn.close()
    return cur.lastrowid


def delete_photo_files(album_id: int, filename: str) -> None:
    for base in (PHOTOS, THUMBS, LARGE):
        (base / str(album_id) / filename).unlink(missing_ok=True)


# ------------------------------------------------------------ responses --
def public_settings() -> dict:
    s = get_settings()
    keys = (
        "site_title", "tagline", "about_title", "about_text",
        "contact_email", "contact_phone", "contact_instagram", "footer_text",
    )
    out = {k: s.get(k, "") for k in keys}
    out["password_changed"] = s.get("password_changed", "0")
    out["hero_photo_id"] = s.get("hero_photo_id", "")
    hero = None
    if out["hero_photo_id"].isdigit():
        conn = db()
        p = conn.execute(
            "SELECT * FROM photos WHERE id = ?", (int(out["hero_photo_id"]),)
        ).fetchone()
        if p:
            hero = photo_dict(p)
        conn.close()
    out["hero"] = hero
    return out


def album_brief(a: sqlite3.Row, cover: dict | None, count: int) -> dict:
    return {
        "id": a["id"],
        "title": a["title"],
        "slug": a["slug"],
        "description": a["description"],
        "position": a["position"],
        "featured": a["featured"],
        "created_at": a["created_at"],
        "photo_count": count,
        "cover": cover,
    }


def post_dict(p: sqlite3.Row, cover: dict | None) -> dict:
    d = dict(p)
    d.pop("cover_id", None)
    d["cover"] = cover
    d["tags"] = [t.strip() for t in (d.get("tags") or "").split(",") if t.strip()]
    return d


# ================================================================== API ==
@app.middleware("http")
async def security_headers(request: Request, call_next):
    """OWASP: podstawowe nagłówki bezpieczeństwa dla kazdej odpowiedzi."""
    resp = await call_next(request)
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    resp.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
    return resp


@app.get("/api/site")
def api_site():
    conn = db()
    albums = conn.execute(
        "SELECT a.*, (SELECT COUNT(*) FROM photos p WHERE p.album_id = a.id) AS cnt "
        "FROM albums a ORDER BY a.position, a.id"
    ).fetchall()
    featured = conn.execute(
        "SELECT * FROM photos WHERE featured = 1 ORDER BY feat_pos, id LIMIT 12"
    ).fetchall()
    posts = conn.execute(
        "SELECT p.*, "
        "(SELECT COUNT(*) FROM photos) AS dummy FROM posts p "
        "WHERE published = 1 ORDER BY created_at DESC, id DESC LIMIT 6"
    ).fetchall()
    out_albums = []
    for a in albums:
        cover = cover_of(conn, a["id"])
        out_albums.append(album_brief(a, cover, a["cnt"]))
    out_posts = [post_dict(p, photo_cover(conn, p["cover_id"])) for p in posts]
    out_featured = []
    for p in featured:
        d = photo_dict(p)
        d["album_slug"] = conn.execute(
            "SELECT slug FROM albums WHERE id = ?", (p["album_id"],)
        ).fetchone()["slug"]
        out_featured.append(d)
    conn.close()
    return {
        "settings": public_settings(),
        "albums": out_albums,
        "featured": out_featured,
        "posts": out_posts,
        "stats": {
            "albums": len(out_albums),
            "photos": sum(a["photo_count"] for a in out_albums),
            "posts": len(out_posts),
        },
    }


@app.get("/api/albums")
def api_albums():
    conn = db()
    rows = conn.execute(
        "SELECT a.*, (SELECT COUNT(*) FROM photos p WHERE p.album_id = a.id) AS cnt "
        "FROM albums a ORDER BY a.position, a.id"
    ).fetchall()
    out = [album_brief(a, cover_of(conn, a["id"]), a["cnt"]) for a in rows]
    conn.close()
    return {"albums": out}


@app.get("/api/albums/{slug}")
def api_album(slug: str):
    conn = db()
    a = conn.execute("SELECT * FROM albums WHERE slug = ?", (slug,)).fetchone()
    if not a:
        conn.close()
        raise HTTPException(status_code=404, detail="Album nie istnieje")
    photos = conn.execute(
        "SELECT * FROM photos WHERE album_id = ? ORDER BY position, id", (a["id"],)
    ).fetchall()
    cover = cover_of(conn, a["id"])
    conn.close()
    return {
        "album": album_brief(a, cover, len(photos)),
        "photos": [photo_dict(p) for p in photos],
    }


@app.get("/api/posts")
def api_posts():
    conn = db()
    rows = conn.execute(
        "SELECT * FROM posts WHERE published = 1 ORDER BY created_at DESC, id DESC"
    ).fetchall()
    out = [post_dict(p, photo_cover(conn, p["cover_id"])) for p in rows]
    conn.close()
    return {"posts": out}


@app.get("/api/posts/{slug}")
def api_post(slug: str):
    conn = db()
    p = conn.execute("SELECT * FROM posts WHERE slug = ? AND published = 1", (slug,)).fetchone()
    if not p:
        conn.close()
        raise HTTPException(status_code=404, detail="Wpis nie istnieje")
    cover = photo_cover(conn, p["cover_id"])
    conn.close()
    return {"post": post_dict(p, cover)}


@app.get("/api/search")
def api_search(q: str = ""):
    q = (q or "").strip()
    if len(q) < 2:
        return {"albums": [], "posts": [], "photos": []}
    like = "%" + q.replace("%", "").replace("_", "") + "%"
    conn = db()
    albums = conn.execute(
        "SELECT a.*, (SELECT COUNT(*) FROM photos p WHERE p.album_id = a.id) AS cnt "
        "FROM albums a WHERE a.title LIKE ? OR a.description LIKE ? "
        "ORDER BY a.position LIMIT 12",
        (like, like),
    ).fetchall()
    posts = conn.execute(
        "SELECT * FROM posts WHERE published = 1 AND "
        "(title LIKE ? OR excerpt LIKE ? OR content LIKE ? OR tags LIKE ?) "
        "ORDER BY created_at DESC LIMIT 12",
        (like, like, like, like),
    ).fetchall()
    photos = conn.execute(
        "SELECT * FROM photos WHERE title LIKE ? OR description LIKE ? "
        "ORDER BY created_at DESC LIMIT 18",
        (like, like),
    ).fetchall()
    out_a = [album_brief(a, cover_of(conn, a["id"]), a["cnt"]) for a in albums]
    out_p = [post_dict(p, photo_cover(conn, p["cover_id"])) for p in posts]
    out_ph = []
    for p in photos:
        d = photo_dict(p)
        d["album_slug"] = conn.execute(
            "SELECT slug FROM albums WHERE id = ?", (p["album_id"],)
        ).fetchone()["slug"]
        out_ph.append(d)
    conn.close()
    return {"albums": out_a, "posts": out_p, "photos": out_ph}


@app.post("/api/contact")
async def api_contact(request: Request):
    rate_check(request, "contact")
    body = await request.json()
    name = str(body.get("name", "")).strip()[:120]
    email = str(body.get("email", "")).strip()[:200]
    message = str(body.get("message", "")).strip()[:4000]
    if body.get("website"):  # honeypot
        return {"ok": True}
    if not message or not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email):
        raise HTTPException(status_code=400, detail="Uzupełnij poprawnie formularz")
    conn = db()
    conn.execute(
        "INSERT INTO messages (name, email, message) VALUES (?, ?, ?)", (name, email, message)
    )
    conn.commit()
    conn.close()
    return {"ok": True}


# ----------------------------------------------------------------- auth --
@app.post("/api/login")
async def api_login(request: Request):
    rate_check(request, "login")
    body = await request.json()
    if not verify_password(str(body.get("password", ""))):
        raise HTTPException(status_code=401, detail="Błędne hasło")
    token = make_token(secrets.token_hex(16))
    resp = JSONResponse({"ok": True})
    resp.set_cookie(
        SESSION_COOKIE, token, httponly=True, samesite="lax",
        max_age=SESSION_DAYS * 86400, path="/",
    )
    return resp


@app.post("/api/logout")
def api_logout():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(SESSION_COOKIE, path="/")
    return resp


@app.get("/api/me")
def api_me(request: Request):
    session = get_session(request)
    return {
        "authed": bool(session),
        "csrf": session.get("csrf", "") if session else "",
        "password_changed": get_settings().get("password_changed", "0") == "1",
    }


# ----------------------------------------------------------- admin: core --
@app.get("/api/admin/stats")
def api_stats(request: Request):
    require_admin(request)
    conn = db()
    counts = {
        "albums": conn.execute("SELECT COUNT(*) FROM albums").fetchone()[0],
        "photos": conn.execute("SELECT COUNT(*) FROM photos").fetchone()[0],
        "posts": conn.execute("SELECT COUNT(*) FROM posts").fetchone()[0],
        "messages": conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0],
        "unread": conn.execute("SELECT COUNT(*) FROM messages WHERE read = 0").fetchone()[0],
    }
    recent = conn.execute(
        "SELECT * FROM messages ORDER BY created_at DESC, id DESC LIMIT 5"
    ).fetchall()
    conn.close()
    return {"stats": counts, "recent_messages": [dict(r) for r in recent]}


# ---------------------------------------------------------- admin: albums --
@app.get("/api/admin/albums")
def admin_albums(request: Request):
    require_admin(request)
    conn = db()
    rows = conn.execute(
        "SELECT a.*, (SELECT COUNT(*) FROM photos p WHERE p.album_id = a.id) AS cnt "
        "FROM albums a ORDER BY a.position, a.id"
    ).fetchall()
    out = [album_brief(a, cover_of(conn, a["id"]), a["cnt"]) for a in rows]
    conn.close()
    return {"albums": out}


@app.post("/api/admin/albums")
async def admin_create_album(request: Request):
    require_admin(request)
    body = await request.json()
    title = str(body.get("title", "")).strip()
    if not title:
        raise HTTPException(status_code=400, detail="Podaj tytuł albumu")
    slug = unique_slug(title, "albums")
    conn = db()
    pos = next_position(conn, "albums", "1 = 1", ())
    cur = conn.execute(
        "INSERT INTO albums (title, slug, description, position, featured) VALUES (?, ?, ?, ?, ?)",
        (title, slug, str(body.get("description", "")).strip()[:2000], pos,
         1 if body.get("featured") else 0),
    )
    conn.commit()
    conn.close()
    return {"id": cur.lastrowid, "slug": slug}


@app.patch("/api/admin/albums/{album_id}")
async def admin_update_album(request: Request, album_id: int):
    require_admin(request)
    body = await request.json()
    conn = db()
    a = conn.execute("SELECT * FROM albums WHERE id = ?", (album_id,)).fetchone()
    if not a:
        conn.close()
        raise HTTPException(status_code=404, detail="Album nie istnieje")
    title = str(body.get("title", "")).strip() or a["title"]
    featured = 1 if body.get("featured") else 0
    cover_id = body.get("cover_id")
    if cover_id:
        p = conn.execute(
            "SELECT id FROM photos WHERE id = ? AND album_id = ?", (cover_id, album_id)
        ).fetchone()
        cover_id = p["id"] if p else None
    conn.execute(
        "UPDATE albums SET title = ?, description = ?, featured = ?, cover_id = ? WHERE id = ?",
        (title, str(body.get("description", "")).strip()[:2000], featured, cover_id, album_id),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@app.delete("/api/admin/albums/{album_id}")
def admin_delete_album(request: Request, album_id: int):
    require_admin(request)
    conn = db()
    conn.execute("UPDATE posts SET cover_id = NULL WHERE cover_id IN "
                 "(SELECT id FROM photos WHERE album_id = ?)", (album_id,))
    conn.execute("DELETE FROM albums WHERE id = ?", (album_id,))
    conn.commit()
    conn.close()
    import shutil
    for base in (PHOTOS, THUMBS, LARGE):
        shutil.rmtree(base / str(album_id), ignore_errors=True)
    return {"ok": True}


@app.post("/api/admin/albums/reorder")
async def admin_reorder_albums(request: Request):
    require_admin(request)
    body = await request.json()
    conn = db()
    for i, aid in enumerate(body.get("ids", [])):
        conn.execute("UPDATE albums SET position = ? WHERE id = ?", (i, int(aid)))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/api/admin/albums/{album_id}/photos")
async def admin_upload(request: Request, album_id: int,
                       files: list[UploadFile] = File(...)):
    require_admin(request)
    conn = db()
    if not conn.execute("SELECT 1 FROM albums WHERE id = ?", (album_id,)).fetchone():
        conn.close()
        raise HTTPException(status_code=404, detail="Album nie istnieje")
    conn.close()
    added = []
    for f in files:
        if f and f.filename:
            pid = save_upload(album_id, f)
            if pid:
                added.append(pid)
    return {"ok": True, "added": added, "count": len(added)}


@app.patch("/api/admin/photos/{photo_id}")
async def admin_update_photo(request: Request, photo_id: int):
    require_admin(request)
    body = await request.json()
    conn = db()
    p = conn.execute("SELECT * FROM photos WHERE id = ?", (photo_id,)).fetchone()
    if not p:
        conn.close()
        raise HTTPException(status_code=404, detail="Zdjęcie nie istnieje")
    conn.execute(
        "UPDATE photos SET title = ?, description = ? WHERE id = ?",
        (
            str(body.get("title", p["title"] or "")).strip()[:200],
            str(body.get("description", p["description"] or "")).strip()[:1000],
            photo_id,
        ),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/api/admin/photos/reorder")
async def admin_reorder_photos(request: Request):
    require_admin(request)
    body = await request.json()
    conn = db()
    album_id = int(body.get("album_id"))
    for i, pid in enumerate(body.get("ids", [])):
        conn.execute(
            "UPDATE photos SET position = ? WHERE id = ? AND album_id = ?",
            (i, int(pid), album_id),
        )
    conn.commit()
    conn.close()
    return {"ok": True}


@app.delete("/api/admin/photos/{photo_id}")
def admin_delete_photo(request: Request, photo_id: int):
    require_admin(request)
    conn = db()
    p = conn.execute("SELECT * FROM photos WHERE id = ?", (photo_id,)).fetchone()
    if not p:
        conn.close()
        raise HTTPException(status_code=404, detail="Zdjęcie nie istnieje")
    album_id = p["album_id"]
    conn.execute("UPDATE posts SET cover_id = NULL WHERE cover_id = ?", (photo_id,))
    conn.execute("DELETE FROM photos WHERE id = ?", (photo_id,))
    refresh_cover(conn, album_id)
    conn.commit()
    conn.close()
    delete_photo_files(album_id, p["filename"])
    return {"ok": True}


# ------------------------------------------------------------ admin: blog --
@app.get("/api/admin/posts")
def admin_posts(request: Request):
    require_admin(request)
    conn = db()
    rows = conn.execute("SELECT * FROM posts ORDER BY created_at DESC, id DESC").fetchall()
    out = [post_dict(p, photo_cover(conn, p["cover_id"])) for p in rows]
    conn.close()
    return {"posts": out}


@app.get("/api/admin/photos")
def admin_all_photos(request: Request):
    """Lista wszystkich zdjęć — picker okładki dla bloga i hero."""
    require_admin(request)
    conn = db()
    rows = conn.execute(
        "SELECT p.*, a.slug AS album_slug FROM photos p "
        "JOIN albums a ON a.id = p.album_id ORDER BY p.created_at DESC, p.id DESC LIMIT 600"
    ).fetchall()
    out = []
    for p in rows:
        d = dict(p)
        d.update(photo_paths(d))
        out.append(d)
    conn.close()
    return {"photos": out}


@app.get("/api/admin/featured")
def admin_featured(request: Request):
    """Wszystkie zdjęcia + które są wyróżnione (sekcja "Wybrane prace")."""
    require_admin(request)
    conn = db()
    rows = conn.execute(
        "SELECT p.*, a.slug AS album_slug FROM photos p "
        "JOIN albums a ON a.id = p.album_id "
        "ORDER BY p.feat_pos, p.id LIMIT 800"
    ).fetchall()
    out = []
    for p in rows:
        d = dict(p)
        d.update(photo_paths(d))
        out.append(d)
    conn.close()
    return {"photos": out}


@app.post("/api/admin/featured")
async def admin_set_featured(request: Request):
    """Ustaw listę, kolejność i rozmiary wyróżnionych zdjęć (max 12)."""
    require_admin(request)
    body = await request.json()
    ids = [int(x) for x in body.get("ids", [])][:12]
    sizes = body.get("sizes", {}) or {}
    conn = db()
    conn.execute("UPDATE photos SET featured = 0, feat_pos = 0, feat_size = ''")
    for i, pid in enumerate(ids):
        size = str(sizes.get(str(pid), "")).strip()
        if size not in ("wide", "std", "full"):
            size = ""
        conn.execute(
            "UPDATE photos SET featured = 1, feat_pos = ?, feat_size = ? WHERE id = ?",
            (i, size, pid),
        )
    conn.commit()
    conn.close()
    return {"ok": True}


@app.post("/api/admin/posts")
async def admin_create_post(request: Request):
    require_admin(request)
    body = await request.json()
    title = str(body.get("title", "")).strip()
    if not title:
        raise HTTPException(status_code=400, detail="Podaj tytuł wpisu")
    slug = unique_slug(title, "posts")
    conn = db()
    cur = conn.execute(
        "INSERT INTO posts (title, slug, excerpt, content, tags, cover_id, published) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            title,
            slug,
            str(body.get("excerpt", "")).strip()[:600],
            str(body.get("content", "")).strip(),
            ", ".join(t.strip() for t in body.get("tags", []) if t.strip())[:400],
            int(body.get("cover_id", 0)) or None,
            1 if body.get("published", True) else 0,
        ),
    )
    conn.commit()
    conn.close()
    return {"id": cur.lastrowid, "slug": slug}


@app.patch("/api/admin/posts/{post_id}")
async def admin_update_post(request: Request, post_id: int):
    require_admin(request)
    body = await request.json()
    conn = db()
    p = conn.execute("SELECT * FROM posts WHERE id = ?", (post_id,)).fetchone()
    if not p:
        conn.close()
        raise HTTPException(status_code=404, detail="Wpis nie istnieje")
    cover_id = body.get("cover_id")
    if cover_id is None and p["cover_id"]:
        cover_id = p["cover_id"]
    elif cover_id is not None:
        cover_id = int(cover_id) or None
    conn.execute(
        "UPDATE posts SET title = ?, excerpt = ?, content = ?, tags = ?, cover_id = ?, "
        "published = ?, updated_at = datetime('now','localtime') WHERE id = ?",
        (
            str(body.get("title", p["title"])).strip(),
            str(body.get("excerpt", p["excerpt"] or "")).strip()[:600],
            str(body.get("content", p["content"])).strip(),
            ", ".join(t.strip() for t in body.get("tags", []))[:400],
            cover_id,
            1 if body.get("published", True) else 0,
            post_id,
        ),
    )
    conn.commit()
    conn.close()
    return {"ok": True}


@app.delete("/api/admin/posts/{post_id}")
def admin_delete_post(request: Request, post_id: int):
    require_admin(request)
    conn = db()
    conn.execute("DELETE FROM posts WHERE id = ?", (post_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


# -------------------------------------------------------- admin: messages --
@app.get("/api/admin/messages")
def admin_messages(request: Request):
    require_admin(request)
    conn = db()
    rows = conn.execute("SELECT * FROM messages ORDER BY created_at DESC, id DESC").fetchall()
    conn.close()
    return {"messages": [dict(r) for r in rows]}


@app.patch("/api/admin/messages/{message_id}")
async def admin_message_toggle(request: Request, message_id: int):
    require_admin(request)
    body = await request.json()
    conn = db()
    conn.execute("UPDATE messages SET read = ? WHERE id = ?",
                 (1 if body.get("read", True) else 0, message_id))
    conn.commit()
    conn.close()
    return {"ok": True}


@app.delete("/api/admin/messages/{message_id}")
def admin_delete_message(request: Request, message_id: int):
    require_admin(request)
    conn = db()
    conn.execute("DELETE FROM messages WHERE id = ?", (message_id,))
    conn.commit()
    conn.close()
    return {"ok": True}


# --------------------------------------------------------- admin: settings --
@app.get("/api/admin/settings")
def admin_settings(request: Request):
    require_admin(request)
    s = get_settings()
    out = {k: s.get(k, "") for k in s}
    out.pop("admin_password_hash", None)
    out.pop("admin_password_salt", None)
    return {"settings": out}


@app.patch("/api/admin/settings")
async def admin_save_settings(request: Request):
    require_admin(request)
    body = await request.json()
    current = get_settings()
    for key in (
        "site_title", "tagline", "about_title", "about_text",
        "contact_email", "contact_phone", "contact_instagram",
        "footer_text", "hero_photo_id",
    ):
        if key in body:
            value = str(body.get(key, "")).strip()
            # nazwa strony nigdy nie moze byc pusta — wracamy do poprzedniej
            if key == "site_title" and not value:
                value = current.get("site_title", "") or "Dawid — Fotografia"
            set_setting(key, value)
    new_pw = str(body.get("new_password", "") or "")
    if new_pw:
        if new_pw != str(body.get("confirm_password", "") or ""):
            raise HTTPException(status_code=400, detail="Hasła się różnią")
        if len(new_pw) < 6:
            raise HTTPException(status_code=400, detail="Hasło musi mieć min. 6 znaków")
        salt = secrets.token_hex(16)
        set_setting("admin_password_salt", salt)
        set_setting("admin_password_hash", hash_password(new_pw, salt))
        set_setting("password_changed", "1")
    return {"ok": True}


# ---------------------------------------------------------------- media --
app.mount("/media", StaticFiles(directory=PHOTOS), name="media")
app.mount("/thumbs", StaticFiles(directory=THUMBS), name="thumbs")
app.mount("/large", StaticFiles(directory=LARGE), name="large")
app.mount("/static", NoCacheStaticFiles(directory=PUBLIC), name="static")

_INDEX = PUBLIC / "index.html"


@app.get("/{path:path}", include_in_schema=False)
def spa_fallback(path: str):
    """SPA: wszystkie nieznane ścieżki zwracają index.html (frontend routuje)."""
    if path.startswith(("api/", "media/", "thumbs/", "large/", "static/")):
        raise HTTPException(status_code=404)
    if _INDEX.exists():
        return FileResponse(_INDEX)
    return JSONResponse({"detail": "Frontend nie został jeszcze zbudowany"}, status_code=404)


# ------------------------------------------------------------------ run --
init_db()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)

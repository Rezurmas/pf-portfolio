"""Jednorazowa regeneracja: WebP dla wszystkich thumb/large + wymiary w DB.
Uruchom: .venv/Scripts/python tools/regen_webp.py
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import app  # noqa: F401

from PIL import Image


def main() -> None:
    conn = app.db()
    rows = conn.execute("SELECT id, album_id, filename FROM photos").fetchall()
    done = 0
    for r in rows:
        tp = app.THUMBS / str(r["album_id"]) / r["filename"]
        lp = app.LARGE / str(r["album_id"]) / r["filename"]
        try:
            with Image.open(tp) as im:
                tw, th = im.size
            if not (app.THUMBS / str(r["album_id"]) / (r["filename"] + ".webp")).exists():
                with Image.open(tp) as im:
                    im.convert("RGB").save(
                        app.THUMBS / str(r["album_id"]) / (r["filename"] + ".webp"),
                        "WEBP", quality=82,
                    )
            if not (app.LARGE / str(r["album_id"]) / (r["filename"] + ".webp")).exists():
                with Image.open(lp) as im:
                    im.convert("RGB").save(
                        app.LARGE / str(r["album_id"]) / (r["filename"] + ".webp"),
                        "WEBP", quality=88,
                    )
            conn.execute("UPDATE photos SET tw = ?, th = ? WHERE id = ?", (tw, th, r["id"]))
            done += 1
        except Exception as e:
            print("BLAD", r["id"], e)
    conn.commit()
    conn.close()
    print("przetworzono:", done)


if __name__ == "__main__":
    main()

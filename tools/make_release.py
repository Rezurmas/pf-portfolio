"""
Buduje paczkę release pf-portfolio-vX.zip — gotową do wypakowania na serwerze.
Zawiera: kod, frontend, bazę, miniatury i wersje large (BEZ oryginałów zdjęć —
download w lightboxie spada wtedy na large). start.sh + pf.service w deploy/.
Użycie: .venv/Scripts/python tools/make_release.py
"""
import zipfile
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DIST = BASE / "dist"
VERSION = "1.0.0"
NAME = f"pf-portfolio-v{VERSION}"


def build() -> None:
    DIST.mkdir(exist_ok=True)
    out = DIST / f"{NAME}.zip"
    if out.exists():
        out.unlink()

    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        for f in ("app.py", "seed.py", "requirements.txt", "run.bat", "README.md"):
            p = BASE / f
            if p.exists():
                z.write(p, f"{NAME}/{f}")
        for d in ("public", "deploy"):
            for p in (BASE / d).rglob("*"):
                if p.is_file() and "__pycache__" not in p.parts:
                    z.write(p, f"{NAME}/{p.relative_to(BASE)}")
        # baza + lekkie wersje zdjęć
        dbp = BASE / "data" / "site.db"
        if dbp.exists():
            z.write(dbp, f"{NAME}/data/site.db")
        for sub in ("thumbs", "large"):
            for p in (BASE / "data" / sub).rglob("*"):
                if p.is_file():
                    z.write(p, f"{NAME}/data/{sub}/{p.relative_to(BASE / 'data' / sub)}")
        # pusty katalog na przyszłe oryginały z uploadów
        z.writestr(f"{NAME}/data/photos/.keep", "")

    size_mb = out.stat().st_size / 1_000_000
    print(f"OK: {out.name} ({size_mb:.1f} MB)")


if __name__ == "__main__":
    build()

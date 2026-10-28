"""Audyt połączeń: trasy API vs fetch, id vs DOM, klasy JS vs CSS."""
import re
from pathlib import Path

root = Path(__file__).resolve().parent.parent
app_py = (root / "app.py").read_text(encoding="utf-8")
app_js = (root / "public/js/app.js").read_text(encoding="utf-8")
admin_js = (root / "public/js/admin.js").read_text(encoding="utf-8")
index_html = (root / "public/index.html").read_text(encoding="utf-8")
style_css = (root / "public/css/style.css").read_text(encoding="utf-8")

# 1) trasy API zdefiniowane
routes = set(re.findall(r'@app\.(?:get|post|patch|delete|put)\("(/api[^"{]*)', app_py))
# trasy z parametrami: /api/albums/{slug} -> /api/albums/<slug> (fetch używa obu notacji)
routes_norm = {r.replace("{", "<").replace("}", ">") for r in routes}

# 2) wywołania API w JS (fetch i helper api())
fetches = set(re.findall(r"fetch\(\s*[\"'](/api[^\"']*)", app_js + admin_js))
fetches |= set(re.findall(r"fetch\(\s*`(/api[^`]*)", app_js + admin_js))
fetches |= set(re.findall(r"api\(\s*[\"'](/api[^\"']*)", app_js + admin_js))
fetches |= set(re.findall(r"api\(\s*`(/api[^`]*)", app_js + admin_js))
# wyodrębnij stały prefix (do pierwszej zmiennej)
def norm(f: str) -> str:
    f = f.split("${")[0].split("?")[0].rstrip("/")
    return f
fetch_prefixes = {norm(f) for f in fetches}

# sprawdź: każdy prefix fetcha ma pasującą trasę
missing = []
for f in sorted(fetch_prefixes):
    if f and not any(f == r or r.startswith(f + "/") or f.startswith(r.rstrip("}").rstrip(">") + "/") for r in routes_norm):
        # dopasowanie z parametrami: /api/albums/xyz vs /api/albums/<slug>
        ok = False
        for r in routes_norm:
            if "<" in r:
                prefix = r.split("<")[0].rstrip("/")
                if f.startswith(prefix):
                    ok = True
                    break
        if not ok:
            missing.append(f)
print("== fetch bez pasującej trasy ==")
print("\n".join(missing) or "brak")

# trasy nigdy nie używane w JS (informacyjnie)
print("\n== trasy nieużywane w JS ==")
used = []
for r in sorted(routes):
    base = r.split("{")[0].split("<")[0].rstrip("/")
    if not any(base in f for f in fetch_prefixes):
        used.append(r)
print("\n".join(used) or "wszystkie używane")

# 3) id: JS wymaga, index.html + szablony JS dostarczają
ids_in_html = set(re.findall(r'id="([^"]+)"', index_html))
ids_in_js_templates = set(re.findall(r'id="([^"]+)"', app_js + admin_js))
ids_available = ids_in_html | ids_in_js_templates
ids_used = set(re.findall(r'\$\("#([\w-]+)"\)', app_js + admin_js))
ids_used |= set(re.findall(r'getElementById\(["\']([\w-]+)["\']\)', app_js + admin_js))
ids_used |= set(re.findall(r'querySelector\(["\']#([\w-]+)["\']\)', app_js + admin_js))
ids_missing = ids_used - ids_available
print("\n== id użyte w JS bez definicji ==")
print("\n".join(sorted(ids_missing)) or "brak")

# 4) klasy: JS używa, CSS definiuje
css_classes = set(re.findall(r"\.([a-zA-Z][\w-]+)", style_css))
js_classes = set(re.findall(r"classList\.(?:add|remove|toggle)\([\"']([\w-]+)", app_js + admin_js))
js_classes |= set(re.findall(r"className\s*=\s*[\"']([^\"']+)[\"']", app_js + admin_js))
# rozbij wartości className na słowa
cls_words = set()
for c in set(re.findall(r"className\s*=\s*[\"']([^\"']+)[\"']", app_js + admin_js)):
    cls_words |= set(c.split())
# klasy z szablonów
tpl = set(re.findall(r'class="([^"]+)"', app_js + admin_js))
for c in tpl:
    cls_words |= set(c.split())
cls_missing = cls_words - css_classes - {"on", "open", "color", "active"}
print("\n== klasy używane w JS bez definicji w CSS ==")
print("\n".join(sorted(cls_missing)) or "brak")

# 5) zdjęcia w bazie vs pliki na dysku
import sqlite3
conn = sqlite3.connect(root / "data/site.db")
conn.row_factory = sqlite3.Row
rows = conn.execute("SELECT id, album_id, filename FROM photos").fetchall()
missing_files = []
for r in rows:
    t = root / "data/thumbs" / str(r["album_id"]) / r["filename"]
    l = root / "data/large" / str(r["album_id"]) / r["filename"]
    if not t.exists() or not l.exists():
        missing_files.append(r["id"])
print("\n== zdjęcia w DB bez plików thumb/large ==")
print(missing_files or "brak")
# okładki albumów
cols = [r[1] for r in conn.execute("PRAGMA table_info(albums)").fetchall()]
cov_col = "cover_photo_id" if "cover_photo_id" in cols else "cover_id"
alb = conn.execute(f"SELECT id, title, {cov_col} AS cov FROM albums").fetchall()
print("\n== albumy bez okładki ==")
print([(a["id"], a["title"]) for a in alb if not a["cov"]] or "brak")
conn.close()

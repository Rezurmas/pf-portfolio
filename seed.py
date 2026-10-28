"""
Seed — wypełnia świeżą bazę prawdziwymi zdjęciami z pulpitu.
Uruchom: .venv/Scripts/python seed.py
"""
import shutil
import sys
import uuid
from pathlib import Path

from PIL import Image, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parent))
import app  # noqa: F401 — uruchamia init_db()

DESKTOP = Path.home() / "Desktop"
RAJD = DESKTOP / "rajd"
TATA = DESKTOP / "samochod tata"
ZJD = DESKTOP / "zjdecia"
STEEL1 = DESKTOP / "fireee holy steel.jpg"
STEEL2 = DESKTOP / "holysteel 2.jpg"


def add_photo(conn, album_id: int, src: Path, title: str = "", description: str = "") -> int:
    ext = src.suffix.lower()
    if ext not in app.ALLOWED_EXT:
        ext = ".jpg"
    name = uuid.uuid4().hex + ext
    dest = app.PHOTOS / str(album_id) / name
    tdir = app.THUMBS / str(album_id)
    ldir = app.LARGE / str(album_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tdir.mkdir(parents=True, exist_ok=True)
    ldir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dest)

    img = Image.open(dest)
    img = ImageOps.exif_transpose(img)
    taken = app.read_exif_date(dest)
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    img.thumbnail((app.THUMB_SIZE, app.THUMB_SIZE))
    tw, th = img.size
    img.save(tdir / name, "JPEG", quality=85)
    img.save(tdir / (name + ".webp"), "WEBP", quality=82)

    img2 = Image.open(dest)
    img2 = ImageOps.exif_transpose(img2)
    if img2.mode not in ("RGB", "L"):
        img2 = img2.convert("RGB")
    img2.thumbnail((app.LARGE_SIZE, app.LARGE_SIZE))
    img2.save(ldir / name, "JPEG", quality=90)
    img2.save(ldir / (name + ".webp"), "WEBP", quality=88)

    pos = app.next_position(conn, "photos", "album_id = ?", (album_id,))
    cur = conn.execute(
        "INSERT INTO photos (album_id, filename, title, description, position, taken_at, tw, th) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (album_id, name, title, description, pos, taken, tw, th),
    )
    if not conn.execute(
        "SELECT cover_id FROM albums WHERE id = ?", (album_id,)
    ).fetchone()["cover_id"]:
        conn.execute("UPDATE albums SET cover_id = ? WHERE id = ?", (cur.lastrowid, album_id))
    conn.commit()
    return cur.lastrowid


def create_album(conn, title: str, slug: str, description: str, featured: int) -> int:
    pos = app.next_position(conn, "albums", "1 = 1", ())
    cur = conn.execute(
        "INSERT INTO albums (title, slug, description, position, featured) VALUES (?, ?, ?, ?, ?)",
        (title, slug, description, pos, featured),
    )
    conn.commit()
    return cur.lastrowid


def spread(files: list[Path], n: int) -> list[Path]:
    """Równomiernie rozłożony wybór n plików."""
    if len(files) <= n:
        return files
    idxs = {round(i * (len(files) - 1) / (n - 1)) for i in range(n)}
    return [files[i] for i in sorted(idxs)]


def main() -> None:
    conn = app.db()
    # czysta baza
    conn.execute("DELETE FROM messages")
    conn.execute("DELETE FROM posts")
    conn.execute("DELETE FROM albums")  # CASCADE czyści photos
    conn.commit()
    for base in (app.PHOTOS, app.THUMBS, app.LARGE):
        for child in base.iterdir():
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)

    rajd_jpg = sorted(RAJD.glob("*.jpg")) if RAJD.exists() else []
    tata_jpg = sorted(TATA.glob("*.jpg")) if TATA.exists() else []
    zjd_jpg = sorted(ZJD.glob("*.JPG")) + sorted(ZJD.glob("*.jpg")) if ZJD.exists() else []

    # 1. Stal i cegła (featured, hero)
    a1 = create_album(
        conn,
        "Stal i cegła",
        "stal-i-cegla",
        "Miejskie kadry — cegła zdzierająca tynk, stal i światło, które trafia tylko na chwilę. "
        "Brudne ściany zamiast pocztówek.",
        1,
    )
    p_steel1 = add_photo(conn, a1, STEEL1, "Światło na cegle",
                         "Złota godzina na podwórku — stary mur kontra nowy tynk.")
    p_steel2 = add_photo(conn, a1, STEEL2, "Wieża", "Kościół w pochmurny wieczór.")

    # 2. Rajd (featured)
    a2 = create_album(
        conn,
        "Rajd",
        "rajd",
        "Zapis drogi — dworce o złotej godzinie, lasy, ludzie z kijami w dłoniach. "
        "Kadry z wędrówki, nie z pocztówki.",
        1,
    )
    for i, f in enumerate(spread(rajd_jpg, 14)):
        add_photo(conn, a2, f, f"Kadr {i + 1:02d}", "")

    # 3. Samochód taty
    a3 = create_album(
        conn,
        "Samochód taty",
        "samochod-taty",
        "Sesja detali — deska rozdzielcza, skóra, przełączniki. Wnętrze, które opowiada "
        "więcej niż prospekt.",
        0,
    )
    for i, f in enumerate(spread(tata_jpg, 12)):
        add_photo(conn, a3, f, f"Detal {i + 1:02d}", "")

    # 4. Codzienność
    a4 = create_album(
        conn,
        "Codzienność",
        "codziennosc",
        "Rodzina na łące, wiewiórka w liściach, światło w przedziale. Zwykłe dni, "
        "które nie wracają — dlatego je klikam.",
        0,
    )
    for i, f in enumerate(spread(zjd_jpg, 16)):
        add_photo(conn, a4, f, f"Dzień {i + 1:02d}", "")

    # hero
    app.set_setting("hero_photo_id", str(p_steel1))
    app.set_setting("site_title", "Dawid — Fotografia")
    app.set_setting("tagline", "Światło. Kadr. Czerń i biel.")
    app.set_setting(
        "about_text",
        "Cześć. Jestem Dawid — fotografuję to, co inni mijają bez zatrzymania: "
        "światło na cegle, kurz na desce rozdzielczej, cień w lesie.\n\n"
        "Klikam mikro 4/3, bo mały korpus wchodzi tam, gdzie nie wchodzi statyw. "
        "Zbieram kadry z wędrówek, z podwórek i z drogi.\n\n"
        "Ten serwis to mój dom dla tych kadrów: albumy, notatki z plenerów i kontakt.",
    )
    app.set_setting("contact_email", "kontakt@dawid.foto")
    app.set_setting("contact_instagram", "dawid.foto")

    # blog
    def post(title, slug, excerpt, tags, content, cover_id):
        conn.execute(
            "INSERT INTO posts (title, slug, excerpt, content, tags, cover_id, published) "
            "VALUES (?, ?, ?, ?, ?, ?, 1)",
            (title, slug, excerpt, content, tags, cover_id),
        )
        conn.commit()

    post(
        "Dlaczego czerń i biel",
        "dlaczego-czern-i-biel",
        "Kolor rozprasza. Czerń i biel zostawia światło, kształt i ziarno.",
        "fotografia, warsztat",
        "Kolor rozprasza. Gdy kadr robi się monochromatyczny, zostaje to, co naprawdę "
        "liczy: **światło, kształt, faktura**.\n\n"
        "Cegła bez czerwieni to już nie \"stary mur\", tylko mapa cieni. Twarz bez "
        "różu to geometria kości. Ziarno zamiast szumu — historia zamiast snapshotu.\n\n"
        "## Zasady, które sobie narzuciłem\n\n"
        "- Szukam jednego źródła światła, nie trzech\n"
        "- Kontrast buduję w aparacie, nie w edytorze\n"
        "- Jeśli kadr nie działa w skali szarości — nie działa wcale\n\n"
        "> Kolor pokazuje. Czerń i biel pyta.\n\n"
        "Dlatego ta strona jest czarno-biała. To nie filtr — to manifest.",
        p_steel1,
    )
    post(
        "Rajd — zapis drogi",
        "rajd-zapis-drogi",
        "Dworce, lasy i ludzie po drodze. Co zostaje z wędrówki, gdy wyłączy się GPS.",
        "plener, podróż",
        "Wyjechaliśmy bez planu. Telefon w kieszeni, aparat na szyi.\n\n"
        "Pierwszy kadr padł na dworcu — **złota godzina wpadała przez witraże** i rysowała "
        "kratę cieni na posadzce. Nikt nie czekał na pociąg, wszyscy czekali na coś innego.\n\n"
        "Potem las. Ciemny, prawie czarny, a w nim jeden człowiek z kijem i mocnym bocznym "
        "światłem na twarzy. Ten kadr wygrał całą wyprawę.\n\n"
        "Reszta to droga: asfalt, kurz, postoje. Z czternastu klatek wybrałem te, które "
        "coś mówią. Reszta została w katalogu.",
        None,
    )
    post(
        "Mikro 4/3 — dlaczego mały korpus",
        "mikro-4-3-dlaczego-maly-korpus",
        "Mały korpus wchodzi tam, gdzie nie wchodzi statyw. O sprzęcie bez snobizmu.",
        "sprzęt, warsztat",
        "Ludzie pytają, czemu nie pełna klatka. Odpowiadam: **bo pełną klatkę zostawiłbym "
        "w plecaku**.\n\n"
        "Mikro 4/3 ma swoje wady — szum przy wysokim ISO, mniejszą plastykę bokeh. Ale ma "
        "też coś, czego nie ma żaden duży body: *zawsze jest pod ręką*.\n\n"
        "## Mój zestaw\n\n"
        "- korpus mikro 4/3\n"
        "- kitowy zoom + stałka f/1.8\n"
        "- zero statywu, zero lampy — samo światło zastane\n\n"
        "Najlepszy aparat to ten, który masz przy sobie, gdy zapala się ta jedna ściana.",
        p_steel2,
    )

    conn.close()
    print("Seed OK.")
    c = app.db()
    for row in c.execute(
        "SELECT a.title, COUNT(p.id) FROM albums a LEFT JOIN photos p ON p.album_id = a.id "
        "GROUP BY a.id ORDER BY a.position"
    ).fetchall():
        print(f"  - {row['title']}: {row[1]} zdjęć")
    print("  wpisy:", c.execute("SELECT COUNT(*) FROM posts").fetchone()[0])
    c.close()


if __name__ == "__main__":
    main()

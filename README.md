# PF — Portfolio Fotograficzne

Twoja własna strona-portfolio z panelem administratora. Czerń i biel, Times New Roman bold,
ostre krawędzie (zero zaokrągleń), animacje wszędzie: przejścia między stronami, preloader,
kursor, ziarno filmowe, marquee, kenburns w hero, reveal przy scrollu, lightbox z klawiaturą.

## Uruchomienie

```
run.bat
```

Skrypt sam tworzy środowisko (`.venv`) przy pierwszym uruchomieniu, instaluje zależności,
odpala serwer i otwiera przeglądarkę.

- Strona: `http://localhost:8000`
- Panel: `http://localhost:8000/admin`
- Serwer słucha na `0.0.0.0`, więc strona działa też na telefonie w sieci LAN
  (adres komputera, np. `http://192.168.x.x:8000`).

**Logowanie do panelu:** hasło `admin` — zmień je od razu w *Ustawienia → Zmiana hasła*.

## Co potrafi

### Strona publiczna
- **Start** — pełnoekranowe hero z twoim zdjęciem, animowane litery nazwiska, liczniki
  statystyk, wybrane prace, wyróżnione albumy, ostatni wpis z bloga
- **Portfolio** — albumy w dużych rzędach (hover: zdjęcie ożywa w kolorze)
- **Album** — galeria masonry, klik = pełnoekranowy lightbox (strzałki / klawiatura /
  swipe, licznik, pobieranie oryginału, przełącznik B/W)
- **Blog** — wpisy z okładkami, tagami i markdownem (nagłówki, listy, cytaty, kod, obrazy)
- **Kontakt** — formularz z walidacją i animowanym potwierdzeniem; wiadomości lądują
  w panelu (skrzynka)
- **Szukaj** — overlay (przycisk SZUKAJ lub Ctrl+K): albumy, wpisy, zdjęcia na żywo
- **404** — typograficzna strona błędu

### Panel admina (`/admin`)
- Pulpit: statystyki, ostatnie wiadomości
- Albumy: tworzenie, edycja, wyróżnianie, usuwanie; upload zdjęć przeciąganiem
  (wiele plików, paski postępu), zmiana kolejności drag&drop, okładka, tytuły i opisy zdjęć
- Blog: tworzenie/edycja wpisów, podgląd markdown na żywo, okładki z twoich zdjęć,
  publikowanie/szkice
- Wiadomości: czytanie, oznaczanie, usuwanie
- Ustawienia: nazwa strony, tagline, sekcja "O mnie", dane kontaktowe, zdjęcie hero,
  tekst stopki, zmiana hasła

## Technikalia

- **Backend:** FastAPI + SQLite (WAL) + Pillow — zero zewnętrznych usług.
  `data/site.db`, zdjęcia w `data/photos/`, miniatury `data/thumbs/` (900 px),
  wersje do lightboxa `data/large/` (2000 px). Oryginały zostają nietknięte
  (przycisk POBIERZ w lightboxie daje oryginał).
- **Frontend:** czyste SPA (bez frameworków) — `public/index.html`,
  `public/css/style.css`, `public/js/app.js` (strona) i `public/js/admin.js` (panel).
- **Bezpieczeństwo:** hasło pbkdf2 (200k iteracji) z solą, sesja podpisana HMAC (7 dni),
  CSRF na wszystkich operacjach panelu, limit prób logowania, walidacja uploadu po
  magic bytes (nie po rozszerzeniu), sanitacja HTML w markdownie, honeypot w formularzu
  kontaktowym.
- **Seed:** `seed.py` wypełnia bazę twoimi zdjęciami z pulpitu (albumy: *Stal i cegła*,
  *Rajd*, *Samochód taty*, *Codzienność*). Uruchom ponownie, aby zresetować zawartość
  do stanu startowego (uwaga: kasuje aktualne albumy).
- **Testy:** `tests/drive.py` — pełny przejazd headless Chrome przez CDP (strona,
  lightbox, formularz, panel, mobile, search) z liczeniem błędów konsoli.

## Wdrożenie na serwer (Linux / LXC Proxmox)

1. Pobierz paczkę release (`pf-portfolio-vX.zip`) i wypakuj do `/opt`:
   ```bash
   cd /opt
   unzip pf-portfolio-v1.0.0.zip
   mv pf-portfolio-v1.0.0 pf-portfolio
   ```
2. Nadaj prawa i odpal raz, żeby zbudowało `.venv`:
   ```bash
   chmod +x pf-portfolio/start.sh
   ./pf-portfolio/start.sh
   ```
   (Ctrl+C, gdy już widać "Uvicorn running")
3. Zainstaluj usługę systemd — strona wstanie automatycznie przy każdym
   starcie kontenera:
   ```bash
   cp pf-portfolio/deploy/pf.service /etc/systemd/system/pf.service
   systemctl daemon-reload
   systemctl enable --now pf
   ```
4. Status/logi: `systemctl status pf`, `journalctl -u pf -f`.

Paczka release jest "lekka": zawiera miniatury i wersje do lightboxa
(bez oryginałów — przycisk POBIERZ daje wtedy wersję 2000 px). Oryginały
z uploadów w panelu trafiają do `data/photos/`.

## Struktura

```
portfolio/
├── app.py              # backend (API + serwer)
├── seed.py             # wypełnianie bazy zdjęciami
├── run.bat             # start jednym klikiem
├── requirements.txt
├── data/               # baza + zdjęcia (tworzy się automatycznie)
├── public/             # frontend (index.html, css, js)
└── tests/              # skrypty weryfikacyjne (CDP)
```

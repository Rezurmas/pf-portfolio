/* ================================================================
   PF — panel administracyjny (SPA wewnątrz SPA).
   ================================================================ */
"use strict";

(function () {
  const PF = window.PF;
  if (!PF) return;

  const A = {
    root: null,
    me: null,
    csrf: "",
    stats: null,
    albums: [],
    posts: [],
    messages: [],
    settings: null,
    allPhotos: [],
    section: "dash",
    editing: { album: null, post: null },
    uploads: [],
  };

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));
  const esc = PF.esc;
  const toast = PF.toast;
  const md = PF.md;
  const fmtDate = PF.fmtDate;
  const plCount = PF.plCount;

  async function api(path, opts = {}) {
    const res = await fetch(path, {
      headers: { "Content-Type": "application/json", "X-CSRF": A.csrf, ...(opts.headers || {}) },
      credentials: "same-origin",
      ...opts,
    });
    if (!res.ok) {
      let msg = "Błąd " + res.status;
      try { msg = (await res.json()).detail || msg; } catch {}
      throw new Error(msg);
    }
    return res.json();
  }

  /* -------------------------------------------------- layout -- */
  function shell() {
    const navItem = (id, label, badge) => `
      <button class="a-nav-item ${A.section === id ? "active" : ""}" data-sec="${id}">
        <span>${label}</span>${badge ? `<span class="badge">${badge}</span>` : ""}
      </button>`;
    return `
    <div class="admin-shell">
      <aside class="a-side">
        <div class="a-side-head">
          <span class="t">Panel / Admin</span>
          <span class="t" style="color:#777">PF</span>
        </div>
        <nav class="a-nav">
          ${navItem("dash", "Pulpit")}
          ${navItem("albums", "Albumy")}
          ${navItem("blog", "Blog")}
          ${navItem("messages", "Wiadomości", A.stats && A.stats.unread ? A.stats.unread : "")}
          ${navItem("settings", "Ustawienia")}
        </nav>
        <div class="a-side-foot">
          <a class="a-nav-item" href="/" data-link><span>Zobacz stronę</span></a>
          <button class="a-nav-item" id="a-logout"><span>Wyloguj</span></button>
        </div>
      </aside>
      <main class="a-main">
        <section class="a-section ${A.section === "dash" ? "active" : ""}" data-pane="dash">${viewDash()}</section>
        <section class="a-section ${A.section === "albums" ? "active" : ""}" data-pane="albums">${viewAlbums()}</section>
        <section class="a-section ${A.section === "blog" ? "active" : ""}" data-pane="blog">${viewBlog()}</section>
        <section class="a-section ${A.section === "messages" ? "active" : ""}" data-pane="messages">${viewMessages()}</section>
        <section class="a-section ${A.section === "settings" ? "active" : ""}" data-pane="settings">${viewSettings()}</section>
      </main>
    </div>`;
  }

  function go(section) {
    A.section = section;
    A.editing.album = null;
    A.editing.post = null;
    const root = A.root;
    root.innerHTML = shell();
    bindShell();
    if (section === "dash") loadStats();
    if (section === "albums") loadAlbums();
    if (section === "blog") loadPosts();
    if (section === "messages") loadMessages();
    if (section === "settings") loadSettings();
    PF.initReveals(root);
  }

  function bindShell() {
    $$("[data-sec]").forEach((b) => b.addEventListener("click", () => go(b.dataset.sec)));
    $("#a-logout").addEventListener("click", async () => {
      try { await api("/api/logout", { method: "POST" }); } catch {}
      A.me = null;
      renderLogin();
    });
    bindDash(); bindAlbums(); bindBlog(); bindMessages(); bindSettings();
  }

  /* -------------------------------------------------- login -- */
  function renderLogin() {
    const notChanged = A.me && A.me.password_changed === false;
    A.root.innerHTML = `
    <div class="admin-login">
      <form class="login-card" id="login-form" autocomplete="off">
        <div class="lg-title">Panel admina</div>
        <div class="lg-sub">Zaloguj się, by zarządzać stroną</div>
        <div class="field">
          <label for="a-pass">Hasło</label>
          <input id="a-pass" type="password" autocomplete="current-password" name="username" required>
          <span class="bar"></span>
        </div>
        <button class="btn" type="submit" style="width:100%">Wejdź</button>
        ${notChanged ? `<div class="hint">Pierwsze logowanie — domyślne hasło: <strong>admin</strong>. Zmień je w Ustawieniach.</div>` : ""}
        <div class="err" id="login-err"></div>
      </form>
    </div>`;
    const form = $("#login-form");
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const pw = $("#a-pass").value;
      try {
        await api("/api/login", { method: "POST", body: JSON.stringify({ password: pw }) });
        await mount(A.root);
      } catch (err) {
        const card = $(".login-card");
        card.classList.remove("shake");
        void card.offsetWidth;
        card.classList.add("shake");
        const el = $("#login-err");
        el.textContent = err.message;
        el.classList.add("show");
      }
    });
  }

  /* -------------------------------------------------- views -- */
  function viewDash() {
    const s = A.stats || { albums: 0, photos: 0, posts: 0, messages: 0, unread: 0 };
    const card = (n, c) => `<div class="a-card"><div class="num">${n}</div><div class="cap">${c}</div></div>`;
    return `
    <div class="a-head"><h1>Pulpit</h1>
      <div style="display:flex;gap:.7rem;flex-wrap:wrap">
        <button class="a-btn" data-go="albums">Dodaj album</button>
        <button class="a-btn ghost" data-go="blog">Nowy wpis</button>
      </div>
    </div>
    <div class="a-cards">
      ${card(s.albums, "Albumy")}
      ${card(s.photos, "Zdjęcia")}
      ${card(s.posts, "Wpisy")}
      ${card(s.messages, "Wiadomości")}
      ${card(s.unread, "Nieprzeczytane")}
    </div>
    <div class="a-head" style="margin-top:2.6rem"><h1 style="font-size:1rem">Ostatnie wiadomości</h1></div>
    <div class="a-list">
      ${(A.recent || []).map((m) => `
      <div class="a-row">
        <div class="main"><span class="t">${esc(m.name || "Anonim")}</span>
          <span class="s">${esc((m.message || "").slice(0, 110))}</span></div>
        <div class="a-actions"><span class="s" style="font-size:.66rem;letter-spacing:.2em;color:#777">${fmtDate(m.created_at)}</span></div>
      </div>`).join("") || `<div class="a-row"><span class="s">Brak wiadomości.</span></div>`}
    </div>`;
  }

  function viewAlbums() {
    return `
    <div class="a-head"><h1>Albumy</h1>
      <button class="a-btn" id="a-new-album">+ Nowy album</button>
    </div>
    <div id="album-create" style="display:none;margin-bottom:2rem">
      <form class="a-form" id="album-create-form">
        <div class="field"><label>Nazwa albumu</label><input name="title" required maxlength="120"><span class="bar"></span></div>
        <div class="field"><label>Opis</label><textarea name="description" maxlength="2000"></textarea><span class="bar"></span></div>
        <div><label class="a-check"><input type="checkbox" name="featured"> Wyróżniony na stronie głównej</label></div>
        <div><button class="a-btn" type="submit">Utwórz album</button></div>
      </form>
    </div>
    <div class="a-list" id="albums-list"></div>`;
  }

  function albumsListHTML() {
    return A.albums.map((a) => `
    <div class="a-row" data-aid="${a.id}">
      ${a.cover ? `<img class="thumb" src="${a.cover.thumb}" alt="">` : `<div class="thumb" style="display:flex;align-items:center;justify-content:center;color:#555;font-size:.6rem;letter-spacing:.2em">BRAK</div>`}
      <div class="main">
        <span class="t">${esc(a.title)} ${a.featured ? '<span class="badge" style="background:#fff;color:#000;font-size:.6em;padding:.2em .5em;margin-left:.6em;letter-spacing:.2em">WYRÓŻNIONY</span>' : ""}</span>
        <span class="s">${plCount(a.photo_count, "zdjęcie", "zdjęcia", "zdjęć")} / ${fmtDate(a.created_at)}</span>
      </div>
      <div class="a-actions">
        <button class="a-btn mini" data-open-album="${a.id}">Otwórz</button>
        <button class="a-btn mini ghost" data-edit-album="${a.id}">Edytuj</button>
        <button class="a-btn mini danger" data-del-album="${a.id}">Usuń</button>
      </div>
    </div>`).join("") || `<div class="a-row"><span class="s">Brak albumów — utwórz pierwszy.</span></div>`;
  }

  function viewAlbumEditor(album) {
    const photos = album._photos || [];
    return `
    <div class="a-head">
      <h1>${esc(album.title)}</h1>
      <div style="display:flex;gap:.7rem;flex-wrap:wrap">
        <button class="a-btn ghost" data-back-albums>← Albumy</button>
        <button class="a-btn" id="a-save-order" disabled>Zapisz kolejność</button>
      </div>
    </div>
    <form class="a-form" id="album-edit-form" style="max-width:100%;margin-bottom:2rem">
      <div class="row2">
        <div class="field"><label>Nazwa</label><input name="title" value="${esc(album.title)}" maxlength="120"><span class="bar"></span></div>
        <div><label class="a-check" style="margin-top:1.4em"><input type="checkbox" name="featured" ${album.featured ? "checked" : ""}> Wyróżniony</label></div>
      </div>
      <div class="field"><label>Opis</label><textarea name="description" maxlength="2000">${esc(album.description || "")}</textarea><span class="bar"></span></div>
      <div><button class="a-btn" type="submit">Zapisz zmiany</button></div>
    </form>
    <div class="dropzone" id="dropzone">
      <div class="dz-big">Upuść zdjęcia tutaj</div>
      <div class="dz-sub">lub kliknij, aby wybrać pliki (JPG / PNG / WebP, max 40 MB)</div>
      <input type="file" id="file-input" multiple accept=".jpg,.jpeg,.png,.webp,.gif">
    </div>
    <div class="upload-queue" id="upload-queue"></div>
    <div class="a-head" style="margin-top:2.4rem"><h1 style="font-size:1rem">Zdjęcia (${photos.length})</h1></div>
    <div class="a-photos" id="a-photo-grid">${photosGridHTML(photos, album.cover && album.cover.id)}</div>`;
  }

  function photosGridHTML(photos, coverId) {
    return photos.map((p) => `
    <div class="a-photo ${p.id === coverId ? "cover-photo" : ""}" draggable="true" data-pid="${p.id}">
      ${p.id === coverId ? `<span class="cover-tag">OKŁADKA</span>` : ""}
      <img src="${p.thumb}" alt="${esc(p.title || "")}" loading="lazy">
      <div class="ov">
        <div class="ov-top">
          <button class="mini" data-move="${p.id}" data-dir="-1" title="W lewo">←</button>
          <button class="mini" data-move="${p.id}" data-dir="1" title="W prawo">→</button>
        </div>
        <div class="ov-bot">
          <button class="mini" data-edit-photo="${p.id}">Opis</button>
          <button class="mini" data-cover="${p.id}" ${p.id === coverId ? "disabled style=opacity:.4" : ""}>Okładka</button>
          <button class="mini" data-del-photo="${p.id}" style="border-color:#f66">Usuń</button>
        </div>
      </div>
    </div>`).join("") || `<div class="a-row" style="grid-column:1/-1"><span class="s">Brak zdjęć — dodaj przez strefę powyżej.</span></div>`;
  }

  function viewBlog() {
    return `
    <div class="a-head"><h1>Blog</h1>
      <button class="a-btn" id="a-new-post">+ Nowy wpis</button>
    </div>
    <div class="a-list" id="posts-list">
      ${A.posts.map((p) => `
      <div class="a-row">
        ${p.cover ? `<img class="thumb" src="${p.cover.thumb}" alt="">` : ""}
        <div class="main"><span class="t">${esc(p.title)} ${p.published ? "" : '<span style="color:#777;font-size:.6em;letter-spacing:.2em">(SZKIC)</span>'}</span>
          <span class="s">${fmtDate(p.created_at)} / ${(p.tags || []).join(", ")}</span></div>
        <div class="a-actions">
          <button class="a-btn mini" data-edit-post="${p.id}">Edytuj</button>
          <button class="a-btn mini danger" data-del-post="${p.id}">Usuń</button>
        </div>
      </div>`).join("") || `<div class="a-row"><span class="s">Brak wpisów.</span></div>`}
    </div>`;
  }

  function viewPostEditor(post) {
    return `
    <div class="a-head">
      <h1>${post ? "Edytuj wpis" : "Nowy wpis"}</h1>
      <button class="a-btn ghost" data-back-blog>← Blog</button>
    </div>
    <form class="a-form" id="post-form" style="max-width:100%">
      <div class="row2">
        <div class="field"><label>Tytuł</label><input name="title" value="${esc(post ? post.title : "")}" maxlength="200" required><span class="bar"></span></div>
        <div class="field"><label>Tagi (po przecinku)</label><input name="tags" value="${esc(post ? (post.tags || []).join(", ") : "")}" maxlength="400"><span class="bar"></span></div>
      </div>
      <div class="field"><label>Zajawka</label><textarea name="excerpt" maxlength="600">${esc(post ? post.excerpt || "" : "")}</textarea><span class="bar"></span></div>
      <div class="row2">
        <div>
          <div class="field"><label>Treść (markdown)</label></div>
          <textarea name="content" id="post-content" style="min-height:300px;width:100%;background:transparent;border:1px solid var(--line);color:var(--fg);padding:1em;font-family:inherit;font-weight:700">${esc(post ? post.content || "" : "")}</textarea>
        </div>
        <div>
          <div class="field"><label>Podgląd na żywo</label></div>
          <div class="md-preview" id="post-preview"></div>
        </div>
      </div>
      <div class="row2">
        <div class="field"><label>Okładka (zdjęcie)</label>
          <button type="button" class="a-btn ghost" id="pick-cover">${post && post.cover ? "Zmień okładkę" : "Wybierz okładkę"}</button>
          <div id="cover-chosen" style="margin-top:.8rem">${post && post.cover ? `<img src="${post.cover.thumb}" style="width:110px;border:1px solid var(--line)">` : ""}</div>
          <input type="hidden" name="cover_id" value="${post && post.cover ? post.cover.id : ""}">
        </div>
        <div style="padding-top:1.6em"><label class="a-check"><input type="checkbox" name="published" ${post ? (post.published ? "checked" : "") : "checked"}> Opublikowany</label></div>
      </div>
      <div style="display:flex;gap:.8rem">
        <button class="a-btn" type="submit">Zapisz wpis</button>
        ${post ? `<button class="a-btn danger" type="button" id="del-post-btn">Usuń wpis</button>` : ""}
      </div>
    </form>`;
  }

  function viewMessages() {
    return `
    <div class="a-head"><h1>Wiadomości</h1><span class="label">${A.messages.length} łącznie</span></div>
    <div id="messages-list">
      ${A.messages.map((m) => `
      <div class="msg ${m.read ? "" : "unread"}" data-mid="${m.id}">
        <div class="msg-head" data-toggle-msg="${m.id}">
          <span class="m-name">${esc(m.name || "Anonim")}</span>
          <span class="m-meta">${esc(m.email || "")} / ${fmtDate(m.created_at)}</span>
          <div class="a-actions">
            <button class="a-btn mini ghost" data-toggle-read="${m.id}">${m.read ? "Oznacz nieprzeczytaną" : "Oznacz przeczytaną"}</button>
            <button class="a-btn mini danger" data-del-msg="${m.id}">Usuń</button>
          </div>
        </div>
        <div class="msg-body">${esc(m.message || "")}</div>
      </div>`).join("") || `<div class="a-row"><span class="s">Skrzynka pusta.</span></div>`}
    </div>`;
  }

  function viewSettings() {
    const s = A.settings || {};
    const f = (label, key, ph = "") => `
      <div class="field"><label>${label}</label><input name="${key}" value="${esc(s[key] || "")}" placeholder="${ph}"><span class="bar"></span></div>`;
    return `
    <div class="a-head"><h1>Ustawienia</h1></div>
    <form class="a-form" id="settings-form" style="max-width:100%">
      <div class="row2">
        ${f("Nazwa strony", "site_title")}
        ${f("Tagline", "tagline")}
      </div>
      ${f("Tytuł sekcji O mnie", "about_title")}
      <div class="field"><label>Tekst O mnie</label><textarea name="about_text" maxlength="4000">${esc(s.about_text || "")}</textarea><span class="bar"></span></div>
      <div class="row2">
        ${f("E-mail kontaktowy", "contact_email")}
        ${f("Telefon", "contact_phone")}
      </div>
      <div class="row2">
        ${f("Instagram", "contact_instagram", "nazwa bez @")}
        <div class="field"><label>Stopka</label><input name="footer_text" value="${esc(s.footer_text || "")}"><span class="bar"></span></div>
      </div>
      <div class="field"><label>Zdjęcie hero (strona główna)</label>
        <button type="button" class="a-btn ghost" id="pick-hero">${s.hero_photo_id ? "Zmień hero" : "Wybierz hero"}</button>
        <input type="hidden" name="hero_photo_id" value="${esc(s.hero_photo_id || "")}">
      </div>
      <div style="border-top:1px solid var(--line);padding-top:2rem">
        <div class="label" style="margin-bottom:1.2rem">Zmiana hasła</div>
        <div class="row2">
          <div class="field"><label>Nowe hasło (min. 6)</label><input name="new_password" type="password" autocomplete="new-password"><span class="bar"></span></div>
          <div class="field"><label>Powtórz hasło</label><input name="confirm_password" type="password" autocomplete="new-password"><span class="bar"></span></div>
        </div>
      </div>
      <div><button class="a-btn" type="submit">Zapisz ustawienia</button></div>
    </form>`;
  }

  /* -------------------------------------------------- picker -- */
  function openPicker(targetInput, currentId, onPick) {
    if (!A.allPhotos.length) return toast("Brak zdjęć do wyboru", "err");
    const ov = document.createElement("div");
    ov.style.cssText = "position:fixed;inset:0;z-index:5000;background:rgba(0,0,0,.92);display:flex;flex-direction:column;padding:2rem";
    ov.innerHTML = `
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:1.6rem">
        <span class="label">Wybierz zdjęcie</span>
        <button class="a-btn mini ghost" id="pick-close">Zamknij</button>
      </div>
      <div class="picker-grid" style="flex:1">${A.allPhotos.map((p) => `
        <div class="pcell ${p.id === currentId ? "sel" : ""}" data-pick="${p.id}">
          <img src="${p.thumb}" alt="" loading="lazy">
        </div>`).join("")}</div>`;
    document.body.appendChild(ov);
    $("#pick-close", ov).addEventListener("click", () => ov.remove());
    ov.addEventListener("click", (e) => {
      if (e.target === ov) ov.remove();
      const c = e.target.closest("[data-pick]");
      if (c) { ov.remove(); onPick(Number(c.dataset.pick)); }
    });
  }

  /* -------------------------------------------------- photo edit modal -- */
  function openPhotoModal(photo) {
    const ov = document.createElement("div");
    ov.style.cssText = "position:fixed;inset:0;z-index:5000;background:rgba(0,0,0,.92);display:flex;align-items:center;justify-content:center;padding:2rem";
    ov.innerHTML = `
      <div style="width:min(560px,100%);border:1px solid #fff;background:#000;padding:2rem">
        <div class="lg-title" style="font-size:1.2rem;letter-spacing:.2em;text-transform:uppercase;margin-bottom:1.6rem">Opis zdjęcia</div>
        <img src="${photo.large}" alt="" style="width:100%;max-height:38vh;object-fit:contain;border:1px solid var(--line);margin-bottom:1.4rem">
        <div class="field"><label>Tytuł</label><input id="pm-title" value="${esc(photo.title || "")}" maxlength="200"><span class="bar"></span></div>
        <div class="field"><label>Opis</label><textarea id="pm-desc" maxlength="1000">${esc(photo.description || "")}</textarea><span class="bar"></span></div>
        <div style="display:flex;gap:.8rem">
          <button class="a-btn" id="pm-save">Zapisz</button>
          <button class="a-btn ghost" id="pm-close">Anuluj</button>
        </div>
      </div>`;
    document.body.appendChild(ov);
    $("#pm-close", ov).addEventListener("click", () => ov.remove());
    ov.addEventListener("click", (e) => { if (e.target === ov) ov.remove(); });
    $("#pm-save", ov).addEventListener("click", async () => {
      try {
        await api("/api/admin/photos/" + photo.id, {
          method: "PATCH",
          body: JSON.stringify({ title: $("#pm-title", ov).value, description: $("#pm-desc", ov).value }),
        });
        toast("Zapisano");
        ov.remove();
        loadAlbumEditor(A.editing.album);
      } catch (e) { toast(e.message, "err"); }
    });
  }

  /* -------------------------------------------------- bindings -- */
  function bindDash() {
    $$("[data-go]").forEach((b) => b.addEventListener("click", () => go(b.dataset.go)));
  }

  function bindAlbums() {
    const create = $("#album-create"), form = $("#album-create-form");
    $("#a-new-album")?.addEventListener("click", () => {
      create.style.display = create.style.display === "none" ? "block" : "none";
    });
    form?.addEventListener("submit", async (e) => {
      if (form.dataset.editId) return;
      e.preventDefault();
      const d = Object.fromEntries(new FormData(form).entries());
      try {
        const r = await api("/api/admin/albums", {
          method: "POST",
          body: JSON.stringify({ title: d.title, description: d.description, featured: !!d.featured }),
        });
        toast("Album utworzony");
        await loadAlbums();
        await openAlbumEditor(r.id);
      } catch (err) { toast(err.message, "err"); }
    });
    const list = $("#albums-list");
    list?.addEventListener("click", async (e) => {
      const open = e.target.closest("[data-open-album]");
      const edit = e.target.closest("[data-edit-album]");
      const del = e.target.closest("[data-del-album]");
      if (open) { await openAlbumEditor(Number(open.dataset.openAlbum)); return; }
      if (edit) {
        const a = A.albums.find((x) => x.id === Number(edit.dataset.editAlbum));
        if (a) { $("#album-create").style.display = "block"; form.elements.title.value = a.title; form.elements.description.value = a.description; form.elements.featured.checked = !!a.featured; form.dataset.editId = a.id; }
        return;
      }
      if (del) {
        if (!confirm("Usunąć album i wszystkie jego zdjęcia? Tej operacji nie da się cofnąć.")) return;
        try {
          await api("/api/admin/albums/" + del.dataset.delAlbum, { method: "DELETE" });
          toast("Album usunięty");
          await loadAlbums();
        } catch (err) { toast(err.message, "err"); }
      }
    });
    form?.addEventListener("submit", async (e) => {
      if (form.dataset.editId) {
        e.preventDefault();
        const d = Object.fromEntries(new FormData(form).entries());
        try {
          await api("/api/admin/albums/" + form.dataset.editId, {
            method: "PATCH",
            body: JSON.stringify({ title: d.title, description: d.description, featured: !!d.featured }),
          });
          toast("Zapisano");
          form.dataset.editId = "";
          form.reset();
          await loadAlbums();
        } catch (err) { toast(err.message, "err"); }
      }
    });
  }

  async function bindAlbumEditor() {
    const form = $("#album-edit-form");
    form?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const d = Object.fromEntries(new FormData(form).entries());
      try {
        await api("/api/admin/albums/" + A.editing.album, {
          method: "PATCH",
          body: JSON.stringify({ title: d.title, description: d.description, featured: !!d.featured }),
        });
        toast("Zapisano");
      } catch (err) { toast(err.message, "err"); }
    });
    const back = document.querySelector("[data-back-albums]");
    back?.addEventListener("click", () => { go("albums"); });

    /* upload */
    const dz = $("#dropzone"), fi = $("#file-input");
    if (dz && fi) {
      ["dragenter", "dragover"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.add("drag"); }));
      ["dragleave", "drop"].forEach((ev) => dz.addEventListener(ev, (e) => { e.preventDefault(); dz.classList.remove("drag"); }));
      dz.addEventListener("drop", (e) => uploadFiles(e.dataTransfer.files));
      fi.addEventListener("change", () => uploadFiles(fi.files));
    }

    /* siatka zdjęć */
    const grid = $("#a-photo-grid");
    grid?.addEventListener("click", async (e) => {
      const mv = e.target.closest("[data-move]");
      const ed = e.target.closest("[data-edit-photo]");
      const cv = e.target.closest("[data-cover]");
      const dl = e.target.closest("[data-del-photo]");
      if (mv) { await movePhoto(Number(mv.dataset.move), Number(mv.dataset.dir)); return; }
      if (ed) {
        const album = A.albums.find((a) => a.id === A.editing.album);
        const p = album._photos.find((x) => x.id === Number(ed.dataset.editPhoto));
        if (p) openPhotoModal(p);
        return;
      }
      if (cv) {
        try {
          await api("/api/admin/albums/" + A.editing.album, { method: "PATCH", body: JSON.stringify({ cover_id: Number(cv.dataset.cover) }) });
          toast("Okładka ustawiona");
          await loadAlbumEditor(A.editing.album);
        } catch (err) { toast(err.message, "err"); }
        return;
      }
      if (dl) {
        if (!confirm("Usunąć to zdjęcie?")) return;
        try {
          await api("/api/admin/photos/" + dl.dataset.delPhoto, { method: "DELETE" });
          toast("Zdjęcie usunięte");
          await loadAlbumEditor(A.editing.album);
        } catch (err) { toast(err.message, "err"); }
      }
    });

    /* drag&drop kolejności */
    let dragId = null;
    grid?.addEventListener("dragstart", (e) => {
      const cell = e.target.closest(".a-photo");
      if (!cell) return;
      dragId = Number(cell.dataset.pid);
      cell.classList.add("dragging");
      e.dataTransfer.effectAllowed = "move";
    });
    grid?.addEventListener("dragend", () => { $$(".a-photo").forEach((c) => c.classList.remove("dragging")); dragId = null; });
    grid?.addEventListener("dragover", (e) => {
      const cell = e.target.closest(".a-photo");
      if (!cell || dragId == null) return;
      e.preventDefault();
    });
    grid?.addEventListener("drop", (e) => {
      const cell = e.target.closest(".a-photo");
      if (!cell || dragId == null) return;
      e.preventDefault();
      const album = A.albums.find((a) => a.id === A.editing.album);
      const arr = album._photos;
      const from = arr.findIndex((p) => p.id === dragId);
      const to = arr.findIndex((p) => p.id === Number(cell.dataset.pid));
      if (from < 0 || to < 0 || from === to) return;
      const [item] = arr.splice(from, 1);
      arr.splice(to, 0, item);
      grid.innerHTML = photosGridHTML(arr, album.cover && album.cover.id);
      $("#a-save-order").disabled = false;
    });
    $("#a-save-order")?.addEventListener("click", async () => {
      const album = A.albums.find((a) => a.id === A.editing.album);
      try {
        await api("/api/admin/photos/reorder", {
          method: "POST",
          body: JSON.stringify({ album_id: album.id, ids: album._photos.map((p) => p.id) }),
        });
        toast("Kolejność zapisana");
        $("#a-save-order").disabled = true;
      } catch (err) { toast(err.message, "err"); }
    });
  }

  function uploadFiles(files) {
    if (!files || !files.length) return;
    const queue = $("#upload-queue");
    [...files].forEach((file) => {
      const row = document.createElement("div");
      row.className = "uq-item";
      row.innerHTML = `
        <span class="uq-name">${esc(file.name)}</span>
        <span class="uq-bar-wrap"><span class="uq-bar"></span></span>
        <span class="uq-state">0%</span>`;
      queue.appendChild(row);
      const xhr = new XMLHttpRequest();
      const fd = new FormData();
      fd.append("files", file);
      xhr.open("POST", "/api/admin/albums/" + A.editing.album + "/photos");
      xhr.setRequestHeader("X-CSRF", A.csrf);
      xhr.upload.onprogress = (e) => {
        if (!e.lengthComputable) return;
        const pct = Math.round((e.loaded / e.total) * 100);
        row.querySelector(".uq-bar").style.transform = `scaleX(${pct / 100})`;
        row.querySelector(".uq-state").textContent = pct + "%";
      };
      xhr.onload = async () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          row.classList.add("ok");
          row.querySelector(".uq-state").textContent = "OK";
        } else {
          row.classList.add("err");
          row.querySelector(".uq-state").textContent = "BŁĄD";
        }
        setTimeout(() => row.remove(), 1800);
        await loadAlbumEditor(A.editing.album, true);
      };
      xhr.onerror = () => { row.classList.add("err"); row.querySelector(".uq-state").textContent = "BŁĄD"; };
      xhr.send(fd);
    });
  }

  async function movePhoto(pid, dir) {
    const album = A.albums.find((a) => a.id === A.editing.album);
    const arr = album._photos;
    const i = arr.findIndex((p) => p.id === pid);
    const j = i + dir;
    if (i < 0 || j < 0 || j >= arr.length) return;
    [arr[i], arr[j]] = [arr[j], arr[i]];
    try {
      await api("/api/admin/photos/reorder", {
        method: "POST",
        body: JSON.stringify({ album_id: album.id, ids: arr.map((p) => p.id) }),
      });
      await loadAlbumEditor(album.id);
    } catch (err) { toast(err.message, "err"); }
  }

  function bindBlog() {
    $("#a-new-post")?.addEventListener("click", () => openPostEditor(null));
    const list = $("#posts-list");
    list?.addEventListener("click", (e) => {
      const ed = e.target.closest("[data-edit-post]");
      const dl = e.target.closest("[data-del-post]");
      if (ed) { openPostEditor(Number(ed.dataset.editPost)); return; }
      if (dl) {
        if (!confirm("Usunąć wpis?")) return;
        api("/api/admin/posts/" + dl.dataset.delPost, { method: "DELETE" })
          .then(() => { toast("Wpis usunięty"); return loadPosts(); })
          .catch((err) => toast(err.message, "err"));
      }
    });
  }

  async function bindPostEditor(postId) {
    const form = $("#post-form");
    const content = $("#post-content");
    const preview = $("#post-preview");
    const updatePreview = () => { preview.innerHTML = md(content.value); };
    content.addEventListener("input", updatePreview);
    updatePreview();
    document.querySelector("[data-back-blog]")?.addEventListener("click", () => go("blog"));
    $("#pick-cover")?.addEventListener("click", () => {
      const cur = Number(form.elements.cover_id.value) || 0;
      openPicker(null, cur, (id) => {
        form.elements.cover_id.value = id;
        const p = A.allPhotos.find((x) => x.id === id);
        $("#cover-chosen").innerHTML = p ? `<img src="${p.thumb}" style="width:110px;border:1px solid var(--line)">` : "";
      });
    });
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      const d = Object.fromEntries(new FormData(form).entries());
      const body = {
        title: d.title,
        excerpt: d.excerpt,
        content: d.content,
        tags: String(d.tags || "").split(",").map((t) => t.trim()).filter(Boolean),
        cover_id: Number(d.cover_id) || 0,
        published: !!d.published,
      };
      try {
        if (postId) await api("/api/admin/posts/" + postId, { method: "PATCH", body: JSON.stringify(body) });
        else await api("/api/admin/posts", { method: "POST", body: JSON.stringify(body) });
        toast("Wpis zapisany");
        go("blog");
      } catch (err) { toast(err.message, "err"); }
    });
    $("#del-post-btn")?.addEventListener("click", async () => {
      if (!confirm("Usunąć wpis?")) return;
      try { await api("/api/admin/posts/" + postId, { method: "DELETE" }); toast("Wpis usunięty"); go("blog"); }
      catch (err) { toast(err.message, "err"); }
    });
  }

  function bindMessages() {
    const list = $("#messages-list");
    list?.addEventListener("click", async (e) => {
      const tg = e.target.closest("[data-toggle-msg]");
      const tr = e.target.closest("[data-toggle-read]");
      const dl = e.target.closest("[data-del-msg]");
      if (tg) { $(".msg[data-mid='" + tg.dataset.toggleMsg + "']", list).classList.toggle("open"); return; }
      if (tr) {
        const mid = Number(tr.dataset.toggleRead);
        const m = A.messages.find((x) => x.id === mid);
        try {
          await api("/api/admin/messages/" + mid, { method: "PATCH", body: JSON.stringify({ read: !(m && m.read) }) });
          await loadMessages();
        } catch (err) { toast(err.message, "err"); }
        return;
      }
      if (dl) {
        if (!confirm("Usunąć wiadomość?")) return;
        try { await api("/api/admin/messages/" + dl.dataset.delMsg, { method: "DELETE" }); await loadMessages(); }
        catch (err) { toast(err.message, "err"); }
      }
    });
  }

  function bindSettings() {
    $("#settings-form")?.addEventListener("submit", async (e) => {
      e.preventDefault();
      const d = Object.fromEntries(new FormData(e.target).entries());
      try {
        await api("/api/admin/settings", { method: "PATCH", body: JSON.stringify(d) });
        toast("Zapisano");
        await loadSettings();
        PF.navigate("/");
      } catch (err) { toast(err.message, "err"); }
    });
    $("#pick-hero")?.addEventListener("click", () => {
      const cur = Number($("#settings-form").elements.hero_photo_id.value) || 0;
      openPicker(null, cur, (id) => {
        $("#settings-form").elements.hero_photo_id.value = id;
        toast("Hero wybrane — zapisz ustawienia");
      });
    });
  }

  /* -------------------------------------------------- loaders -- */
  async function loadStats() {
    try {
      const r = await api("/api/admin/stats");
      A.stats = r.stats; A.recent = r.recent_messages;
      if (A.section === "dash") { A.root.innerHTML = shell(); bindShell(); }
    } catch (err) { toast(err.message, "err"); }
  }

  async function loadAlbums() {
    try {
      const r = await api("/api/admin/albums");
      A.albums = r.albums;
      const el = $("#albums-list");
      if (el) el.innerHTML = albumsListHTML();
    } catch (err) { toast(err.message, "err"); }
  }

  async function loadAlbumEditor(albumId, keepScroll = false) {
    try {
      const r = await api("/api/admin/albums");
      A.albums = r.albums;
      const pub = await api("/api/albums");
      const album = A.albums.find((a) => a.id === albumId);
      if (!album) return go("albums");
      const full = pub.albums.find((a) => a.id === albumId);
      album._photos = [];
      if (full) {
        const det = await api("/api/albums/" + full.slug);
        album._photos = det.photos;
        album.cover = det.album.cover;
      }
      A.editing.album = albumId;
      const root = A.root;
      const oldScroll = scrollY;
      root.innerHTML = shell();
      /* wstaw widok edytora albumu w miejsce sekcji albums */
      const pane = $('[data-pane="albums"]', root);
      if (pane) { pane.innerHTML = viewAlbumEditor(album); pane.classList.add("active"); }
      bindShell();
      await bindAlbumEditor();
      if (keepScroll) scrollTo(0, oldScroll);
    } catch (err) { toast(err.message, "err"); }
  }

  async function openAlbumEditor(albumId) {
    await loadAlbumEditor(albumId);
  }

  async function loadPosts() {
    try {
      const r = await api("/api/admin/posts");
      A.posts = r.posts;
      const el = $("#posts-list");
      if (el) el.innerHTML = A.posts.map((p) => `
      <div class="a-row">
        ${p.cover ? `<img class="thumb" src="${p.cover.thumb}" alt="">` : ""}
        <div class="main"><span class="t">${esc(p.title)} ${p.published ? "" : '<span style="color:#777;font-size:.6em;letter-spacing:.2em">(SZKIC)</span>'}</span>
          <span class="s">${fmtDate(p.created_at)} / ${(p.tags || []).join(", ")}</span></div>
        <div class="a-actions">
          <button class="a-btn mini" data-edit-post="${p.id}">Edytuj</button>
          <button class="a-btn mini danger" data-del-post="${p.id}">Usuń</button>
        </div>
      </div>`).join("") || `<div class="a-row"><span class="s">Brak wpisów.</span></div>`;
    } catch (err) { toast(err.message, "err"); }
  }

  async function openPostEditor(postId) {
    try {
      if (!A.allPhotos.length) {
        const r = await api("/api/admin/photos");
        A.allPhotos = r.photos;
      }
      const post = postId ? A.posts.find((p) => p.id === postId) : null;
      A.editing.post = postId;
      const root = A.root;
      root.innerHTML = shell();
      const pane = $('[data-pane="blog"]', root);
      if (pane) { pane.innerHTML = viewPostEditor(post); pane.classList.add("active"); }
      bindShell();
      await bindPostEditor(postId);
    } catch (err) { toast(err.message, "err"); }
  }

  async function loadMessages() {
    try {
      const r = await api("/api/admin/messages");
      A.messages = r.messages;
      const el = $("#messages-list");
      if (el) el.innerHTML = r.messages.map((m) => `
      <div class="msg ${m.read ? "" : "unread"}" data-mid="${m.id}">
        <div class="msg-head" data-toggle-msg="${m.id}">
          <span class="m-name">${esc(m.name || "Anonim")}</span>
          <span class="m-meta">${esc(m.email || "")} / ${fmtDate(m.created_at)}</span>
          <div class="a-actions">
            <button class="a-btn mini ghost" data-toggle-read="${m.id}">${m.read ? "Oznacz nieprzeczytaną" : "Oznacz przeczytaną"}</button>
            <button class="a-btn mini danger" data-del-msg="${m.id}">Usuń</button>
          </div>
        </div>
        <div class="msg-body">${esc(m.message || "")}</div>
      </div>`).join("") || `<div class="a-row"><span class="s">Skrzynka pusta.</span></div>`;
    } catch (err) { toast(err.message, "err"); }
  }

  async function loadSettings() {
    try {
      const r = await api("/api/admin/settings");
      A.settings = r.settings;
      const form = $("#settings-form");
      if (form) {
        for (const k of ["site_title", "tagline", "about_title", "about_text",
                         "contact_email", "contact_phone", "contact_instagram",
                         "footer_text", "hero_photo_id"]) {
          const el = form.elements[k];
          if (el) el.value = r.settings[k] || "";
        }
      }
    } catch (err) { toast(err.message, "err"); }
  }

  /* ---------------------------------------------------- mount -- */
  async function mount(root) {
    A.root = root;
    try {
      A.me = await api("/api/me");
      A.csrf = A.me.csrf;
    } catch (e) {
      toast("Brak połączenia z serwerem", "err");
      return;
    }
    if (!A.me.authed) { renderLogin(); return; }
    try {
      const [st, al, po] = await Promise.all([
        api("/api/admin/stats"),
        api("/api/admin/albums"),
        api("/api/admin/posts"),
      ]);
      A.stats = st.stats; A.recent = st.recent_messages;
      A.albums = al.albums; A.posts = po.posts;
    } catch (e) { toast(e.message, "err"); }
    A.section = "dash";
    root.innerHTML = shell();
    bindShell();
  }

  window.PFAdmin = { mount };
})();

/* ================================================================
   PF — frontend. SPA + animacje.
   ================================================================ */
"use strict";

/* ------------------------------------------------------- helpers -- */
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => Array.from(r.querySelectorAll(s));

function esc(s) {
  return String(s ?? "")
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;").replaceAll("'", "&#39;");
}

function fmtDate(s) {
  if (!s) return "";
  const m = String(s).match(/^(\d{4})-(\d{2})-(\d{2})/);
  return m ? `${m[3]}.${m[2]}.${m[1]}` : String(s);
}

/* obrazek z WebP (fallback JPEG) + atrybuty wymiarów (zero CLS) */
function pic(webp, fallback, alt = "", extra = "") {
  return `<picture><source srcset="${webp}" type="image/webp"><img src="${fallback}" alt="${esc(alt)}" ${extra}></picture>`;
}

function dims(p) {
  return p.tw && p.th ? `width="${p.tw}" height="${p.th}" ` : "";
}

function plCount(n, one, few, many) {
  n = Number(n) || 0;
  if (n === 1) return `${n} ${one}`;
  const d = n % 10, h = n % 100;
  if (d >= 2 && d <= 4 && !(h >= 12 && h <= 14)) return `${n} ${few}`;
  return `${n} ${many}`;
}

async function api(path, opts = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(opts.headers || {}) },
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

let _toastTimer = 0;
function toast(msg, type = "ok") {
  const box = $("#toasts");
  const el = document.createElement("div");
  el.className = "toast " + (type === "err" ? "err" : "");
  el.textContent = msg;
  box.appendChild(el);
  setTimeout(() => {
    el.classList.add("out");
    setTimeout(() => el.remove(), 450);
  }, 2600);
}

/* ------------------------------------------------- mini markdown -- */
function md(src) {
  const s = String(src ?? "");
  const holders = [];
  const stash = (html) => { holders.push(html); return `\u0000${holders.length - 1}\u0000`; };
  let t = s
    .replace(/```([\s\S]*?)```/g, (_, c) => stash(`<pre><code>${esc(c.trim())}</code></pre>`))
    .replace(/`([^`]+)`/g, (_, c) => `<code>${esc(c)}</code>`);
  t = esc(t);
  const lines = t.split(/\n/);
  const out = [];
  let list = null;
  const closeList = () => { if (list) { out.push(`</${list}>`); list = null; } };
  for (const raw of lines) {
    const line = raw.trimEnd();
    if (/^\u0000\d+\u0000$/.test(line.trim())) { closeList(); out.push(line.trim()); continue; }
    const h = line.match(/^(#{1,3})\s+(.*)$/);
    if (h) { closeList(); const lvl = h[1].length; out.push(`<h${lvl + 1}>${inlineMd(h[2])}</h${lvl + 1}>`); continue; }
    if (/^---+$/.test(line.trim())) { closeList(); out.push("<hr>"); continue; }
    const bq = line.match(/^&gt;\s?(.*)$/);
    if (bq) { closeList(); out.push(`<blockquote>${inlineMd(bq[1])}</blockquote>`); continue; }
    const ul = line.match(/^\s*[-*]\s+(.*)$/);
    if (ul) { if (list !== "ul") { closeList(); out.push("<ul>"); list = "ul"; } out.push(`<li>${inlineMd(ul[1])}</li>`); continue; }
    const ol = line.match(/^\s*\d+\.\s+(.*)$/);
    if (ol) { if (list !== "ol") { closeList(); out.push("<ol>"); list = "ol"; } out.push(`<li>${inlineMd(ol[1])}</li>`); continue; }
    closeList();
    if (line.trim()) out.push(`<p>${inlineMd(line)}</p>`);
  }
  closeList();
  let html = out.join("\n");
  html = html.replace(/\u0000(\d+)\u0000/g, (_, i) => holders[+i]);
  return html;
}

function inlineMd(s) {
  return s
    .replace(/!\[([^\]]*)\]\(([^)\s]+)\)/g, (_, a, u) => `<img src="${esc(u)}" alt="${esc(a)}" loading="lazy">`)
    .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_, a, u) => `<a href="${esc(u)}" target="_blank" rel="noopener">${a}</a>`)
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*\n]+)\*(?!\*)/g, "$1<em>$2</em>");
}

/* ------------------------------------------------------- stan -- */
const S = {
  site: null,
  path: location.pathname,
  view: null,
};

/* --------------------------------------------------- preloader -- */
function runPreloader(done) {
  const pre = $("#preloader"), num = $("#pre-num");
  if (!pre) return done();
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduce || sessionStorage.getItem("pf_pre_shown")) {
    pre.style.display = "none";
    return done();
  }
  sessionStorage.setItem("pf_pre_shown", "1");
  const t0 = performance.now(), dur = 900;
  const tick = (now) => {
    const p = Math.min(1, (now - t0) / dur);
    const eased = 1 - Math.pow(1 - p, 3);
    num.textContent = String(Math.round(eased * 100)).padStart(2, "0");
    if (p < 1) requestAnimationFrame(tick);
    else { pre.classList.add("done"); setTimeout(() => { pre.remove(); done(); }, 700); }
  };
  requestAnimationFrame(tick);
}

/* ------------------------------------------------------ kursor -- */
function initCursor() {
  const fine = matchMedia("(pointer: fine)").matches;
  if (!fine || matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const dot = $("#cursor-dot"), ring = $("#cursor-ring");
  document.documentElement.classList.add("has-cursor");
  let x = innerWidth / 2, y = innerHeight / 2, rx = x, ry = y;
  addEventListener("mousemove", (e) => {
    x = e.clientX; y = e.clientY;
    dot.style.opacity = ring.style.opacity = "1";
    dot.style.transform = `translate(${x - 4}px, ${y - 4}px)`;
  });
  addEventListener("mouseleave", () => { dot.style.opacity = ring.style.opacity = "0"; });
  (function loop() {
    rx += (x - rx) * 0.16; ry += (y - ry) * 0.16;
    ring.style.transform = `translate(${rx - 17}px, ${ry - 17}px)`;
    requestAnimationFrame(loop);
  })();
  document.addEventListener("mouseover", (e) => {
    ring.classList.toggle("is-big", !!e.target.closest("a, button, input, textarea, [data-cursor]"));
  });
}

/* ------------------------------------------------------ header -- */
function initHeader() {
  const h = $("#site-header");
  let lastY = scrollY;
  addEventListener("scroll", () => {
    const y = scrollY;
    h.classList.toggle("solid", y > 60);
    if (y > lastY && y > 420 && !$("#mobile-menu").classList.contains("open")) h.classList.add("hidden");
    else h.classList.remove("hidden");
    lastY = y;
    const max = document.documentElement.scrollHeight - innerHeight;
    $("#scroll-progress").style.width = (max > 0 ? (y / max) * 100 : 0) + "%";
  }, { passive: true });
  const burger = $("#nav-burger"), menu = $("#mobile-menu");
  burger.addEventListener("click", () => {
    const open = menu.classList.toggle("open");
    h.classList.toggle("menu-open", open);
    document.body.style.overflow = open ? "hidden" : "";
  });
  $$("#mobile-menu a").forEach((a) => a.addEventListener("click", () => {
    menu.classList.remove("open");
    h.classList.remove("menu-open");
    document.body.style.overflow = "";
  }));
}

/* ----------------------------------------------- reveal system -- */
function initReveals(root = document) {
  /* grupy: kontener [data-reveal-group] odpala WSZYSTKIE dzieci kaskadą,
     gdy tylko sam wejdzie w ekran — bez zależności od dalszego scrolla */
  const groupIO = new IntersectionObserver((entries) => {
    for (const en of entries) {
      if (!en.isIntersecting) continue;
      const g = en.target;
      g.dataset.revealGroupDone = "1";
      $$("[data-reveal]", g).forEach((el, i) => {
        if (el.dataset.revealDone) return;
        el.dataset.revealDone = "1";
        if (!el.dataset.delay) el.style.setProperty("--rd", (i * 60) + "ms");
        el.classList.add("is-in");
        const n = el.dataset.count;
        if (n != null) countUp(el, Number(n));
      });
      groupIO.unobserve(g);
    }
  }, { threshold: 0.05, rootMargin: "0px 0px 14% 0px" });

  /* pojedyncze elementy: strefa aktywacji przesunięta wcześniej (14%),
     żeby pojawiały się zanim użytkownik w pełni do nich dojedzie */
  const io = new IntersectionObserver((entries) => {
    for (const en of entries) {
      if (!en.isIntersecting) continue;
      const el = en.target;
      el.dataset.revealDone = "1";
      el.classList.add("is-in");
      const n = el.dataset.count;
      if (n != null) countUp(el, Number(n));
      io.unobserve(el);
    }
  }, { threshold: 0.1, rootMargin: "0px 0px 14% 0px" });

  const els = $$("[data-reveal]", root)
    .filter((el) => !el.dataset.revealDone && !el.closest("[data-reveal-group]"));
  els.forEach((el, i) => {
    const group = el.closest("[data-stagger]");
    if (!el.dataset.delay) {
      const base = group ? i * 45 : 0;
      el.style.setProperty("--rd", base + "ms");
    }
    io.observe(el);
  });
  $$("[data-reveal-group]", root)
    .filter((g) => !g.dataset.revealGroupDone)
    .forEach((g) => groupIO.observe(g));
  return io;
}

function countUp(el, target) {
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduce) { el.textContent = target; return; }
  const t0 = performance.now(), dur = 1300;
  const tick = (now) => {
    const p = Math.min(1, (now - t0) / dur);
    el.textContent = Math.round(target * (1 - Math.pow(1 - p, 3)));
    if (p < 1) requestAnimationFrame(tick);
  };
  requestAnimationFrame(tick);
}

/* ----------------------------------------------------- marquee -- */
function buildMarquees(root = document) {
  $$(".marquee-track", root).forEach((track) => {
    if (track.dataset.built) return;
    track.dataset.built = "1";
    track.innerHTML += track.innerHTML;
  });
}

/* ------------------------------------------------------ parallax -- */
function initParallax() {
  const media = $(".hero-media");
  if (!media) return;
  let ticking = false;
  const onScroll = () => {
    if (ticking) return;
    ticking = true;
    requestAnimationFrame(() => {
      const y = scrollY;
      if (y < innerHeight * 1.2) media.style.transform = `translateY(${y * 0.32}px)`;
      ticking = false;
    });
  };
  addEventListener("scroll", onScroll, { passive: true });
}

/* -------------------------------------------------------- wipe -- */
const wipeEl = () => $("#wipe");
function wipeTransition(over, cb) {
  const w = wipeEl();
  if (!w) return cb();
  w.classList.remove("cover", "reveal");
  void w.offsetWidth;
  w.classList.add(over ? "cover" : "reveal");
  const ms = over ? 500 : 550;
  if (over) setTimeout(cb, ms * 0.72);
  else setTimeout(() => w.classList.remove("reveal"), ms);
}

/* ------------------------------------------------------ router -- */
const routes = {
  "/": renderHome,
  "/portfolio": renderPortfolio,
  "/blog": renderBlog,
  "/kontakt": renderKontakt,
};

function matchRoute(path) {
  if (path === "/admin") return renderAdmin;
  let m = path.match(/^\/portfolio\/([^/]+)$/);
  if (m) return (p) => renderAlbum(m[1]);
  m = path.match(/^\/blog\/([^/]+)$/);
  if (m) return (p) => renderPost(m[1]);
  if (routes[path]) return routes[path];
  return render404;
}

async function render(path) {
  S.path = path;
  const fn = matchRoute(path);
  const html = await fn(path);
  const view = $("#view");
  view.innerHTML = html;
  view.classList.remove("view-in");
  void view.offsetWidth;
  view.classList.add("view-in");
  if (path === "/admin") await mountAdmin();
  afterRender(path);
}

function afterRender(path) {
  setActiveNav(path);
  buildMarquees();
  initReveals();
  initParallax();
  if (path === "/" || path === "") splitHeroTitle();
  if (path === "/kontakt") initContactForm();
  // w panelu chowamy nagłówek strony — sidebar ma własną główkę, zero nakładania
  $("#site-header").style.display = path === "/admin" ? "none" : "";
  scrollTo(0, 0);
  if (path !== "/admin") {
    $("#site-footer").hidden = false;
  } else {
    $("#site-footer").hidden = true;
  }
}

function setActiveNav(path) {
  const map = [
    [/^\/portfolio/, "/portfolio"],
    [/^\/blog/, "/blog"],
    [/^\/kontakt/, "/kontakt"],
    [/^\/admin/, "/admin"],
    [/^\/$/, "/"],
  ];
  const current = (map.find(([re]) => re.test(path)) || [])[1] || "/";
  $$(".nav-links a").forEach((a) => a.classList.toggle("active", a.getAttribute("href") === current));
}

function navigate(path, useWipe = true) {
  if (path === S.path) return;
  closeOverlays();
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) useWipe = false;
  const go = () => render(path).catch((e) => { toast(e.message, "err"); return render404(path); });
  if (useWipe) {
    wipeTransition(true, () => {
      go().then(() => wipeTransition(false));
    });
  } else {
    go();
  }
  history.pushState({}, "", path);
}

addEventListener("popstate", () => {
  const path = location.pathname;
  if (path === S.path) return;
  render(path).catch(() => render404(path));
});

document.addEventListener("click", (e) => {
  const a = e.target.closest("a[data-link]");
  if (!a) return;
  if (e.metaKey || e.ctrlKey || e.shiftKey || e.button !== 0) return;
  const href = a.getAttribute("href");
  if (!href || href.startsWith("http") || href.startsWith("#")) return;
  e.preventDefault();
  navigate(href);
});

/* ------------------------------------------------- hero letters -- */
function splitHeroTitle() {
  $$(".hero-title .line").forEach((line, li) => {
    if (line.dataset.split) return;
    line.dataset.split = "1";
    const text = line.textContent;
    line.textContent = "";
    [...text].forEach((ch, i) => {
      const sp = document.createElement("span");
      sp.className = "l";
      sp.textContent = ch === " " ? "\u00A0" : ch;
      sp.style.animationDelay = `${li * 120 + i * 38}ms`;
      line.appendChild(sp);
    });
  });
}

/* ------------------------------------------------- lightbox -- */
const LB = { photos: [], idx: 0, color: false };
function closeLightbox() {
  $("#lightbox").classList.remove("open");
  document.body.style.overflow = "";
}
function initLightbox() {
  const lb = $("#lightbox"), img = $("#lb-img");
  if (lb.dataset.ready) return;
  lb.dataset.ready = "1";
  const show = () => {
    const p = LB.photos[LB.idx];
    img.onerror = () => {
      const fb = img.dataset.fallback;
      if (fb && img.getAttribute("src") !== fb) img.src = fb;
    };
    img.dataset.fallback = p.large;
    img.src = p.large_webp;
    img.alt = p.title || "zdjęcie";
    img.classList.toggle("color", LB.color);
    $("#lb-title").textContent = p.title || "Bez tytułu";
    $("#lb-desc").textContent = p.description || "";
    $("#lb-count").textContent =
      String(LB.idx + 1).padStart(2, "0") + " / " + String(LB.photos.length).padStart(2, "0");
    $("#lb-dl").href = p.download || p.original;
  };
  const slide = (dir) => {
    if (LB.photos.length < 2) return;
    lb.classList.add(dir < 0 ? "sliding-back" : "sliding");
    setTimeout(() => {
      LB.idx = (LB.idx + dir + LB.photos.length) % LB.photos.length;
      show();
      lb.classList.remove("sliding", "sliding-back");
    }, 220);
  };
  $("#lb-prev").addEventListener("click", () => slide(-1));
  $("#lb-next").addEventListener("click", () => slide(1));
  $("#lb-close").addEventListener("click", closeLightbox);
  $("#lb-bw").addEventListener("click", () => {
    LB.color = !LB.color;
    img.classList.toggle("color", LB.color);
    $("#lb-bw").classList.toggle("on", LB.color);
  });
  lb.addEventListener("click", (e) => { if (e.target === lb || e.target === $(".lb-stage")) closeLightbox(); });
  let tx = 0;
  lb.addEventListener("touchstart", (e) => { tx = e.touches[0].clientX; }, { passive: true });
  lb.addEventListener("touchend", (e) => {
    const dx = e.changedTouches[0].clientX - tx;
    if (Math.abs(dx) > 48) slide(dx > 0 ? -1 : 1);
  }, { passive: true });
  addEventListener("keydown", (e) => {
    if (!lb.classList.contains("open")) return;
    if (e.key === "Escape") closeLightbox();
    if (e.key === "ArrowLeft") slide(-1);
    if (e.key === "ArrowRight") slide(1);
  });
}
function openLightbox(photos, idx) {
  if (!photos.length) return;
  LB.photos = photos; LB.idx = idx; LB.color = false;
  initLightbox();
  const lb = $("#lightbox");
  lb.classList.add("open");
  document.body.style.overflow = "hidden";
  const img = $("#lb-img");
  img.onerror = () => {
    const fb = img.dataset.fallback;
    if (fb && img.getAttribute("src") !== fb) img.src = fb;
  };
  img.dataset.fallback = photos[idx].large;
  img.src = photos[idx].large_webp;
  img.classList.remove("color");
  $("#lb-bw").classList.remove("on");
  $("#lb-title").textContent = photos[idx].title || "Bez tytułu";
  $("#lb-desc").textContent = photos[idx].description || "";
  $("#lb-count").textContent =
    String(idx + 1).padStart(2, "0") + " / " + String(photos.length).padStart(2, "0");
  $("#lb-dl").href = photos[idx].download || photos[idx].original;
}

/* ---------------------------------------------------- search -- */
function initSearch() {
  const ov = $("#search-overlay"), inp = $("#search-input"), res = $("#search-results");
  let timer = 0;
  const open = () => { ov.classList.add("open"); setTimeout(() => inp.focus(), 120); document.body.style.overflow = "hidden"; };
  const close = () => { ov.classList.remove("open"); inp.value = ""; res.innerHTML = ""; document.body.style.overflow = ""; };
  $("#nav-search").addEventListener("click", open);
  $("#search-close").addEventListener("click", close);
  addEventListener("keydown", (e) => {
    if (e.key === "Escape" && ov.classList.contains("open")) close();
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); ov.classList.contains("open") ? close() : open(); }
  });
  inp.addEventListener("input", () => {
    clearTimeout(timer);
    const q = inp.value.trim();
    if (q.length < 2) { res.innerHTML = ""; return; }
    timer = setTimeout(async () => {
      try {
        const r = await api("/api/search?q=" + encodeURIComponent(q));
        res.innerHTML = `
          ${r.albums.length ? `<div class="sr-group"><h4>Albumy</h4>${r.albums.map((a) => `
            <a class="sr-item" href="/portfolio/${a.slug}" data-link>${esc(a.title)}<span class="sr-sub">${plCount(a.photo_count, "zdjęcie", "zdjęcia", "zdjęć")}</span></a>`).join("")}</div>` : ""}
          ${r.posts.length ? `<div class="sr-group"><h4>Blog</h4>${r.posts.map((p) => `
            <a class="sr-item" href="/blog/${p.slug}" data-link>${esc(p.title)}<span class="sr-sub">${fmtDate(p.created_at)}</span></a>`).join("")}</div>` : ""}
          ${r.photos.length ? `<div class="sr-group"><h4>Zdjęcia</h4><div class="sr-photos">${r.photos.map((p) => `
            <a href="/portfolio/${p.album_slug}" data-link><img src="${p.thumb}" alt="${esc(p.title)}" loading="lazy"></a>`).join("")}</div></div>` : ""}
          ${!r.albums.length && !r.posts.length && !r.photos.length ? `<div class="label" style="margin-top:2rem">Brak wyników dla „${esc(q)}”</div>` : ""}
        `;
      } catch (e) { res.innerHTML = `<div class="label">${esc(e.message)}</div>`; }
    }, 240);
  });
  document.addEventListener("click", (e) => {
    if (ov.classList.contains("open") && e.target.closest("[data-link]")) close();
  });
}

function closeOverlays() {
  $("#search-overlay").classList.remove("open");
  $("#lightbox").classList.remove("open");
  document.body.style.overflow = "";
}

/* --------------------------------------------------- kontakt -- */
function initContactForm() {
  const form = $("#contact-form");
  if (!form || form.dataset.ready) return;
  form.dataset.ready = "1";
  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = $("button[type=submit]", form);
    const data = Object.fromEntries(new FormData(form).entries());
    btn.disabled = true;
    btn.textContent = "Wysyłanie…";
    try {
      await api("/api/contact", { method: "POST", body: JSON.stringify(data) });
      form.style.display = "none";
      const ok = $("#form-success");
      ok.classList.add("show");
    } catch (err) {
      toast(err.message, "err");
      btn.disabled = false;
      btn.textContent = "Wyślij";
    }
  });
}

/* =================================================== widoki ===== */
function heroNavSpace() {
  return `<div class="wrap" style="padding-top:calc(76px + clamp(2.5rem,7vh,5rem))"></div>`;
}

async function renderHome() {
  const s = S.site;
  const hero = s.settings.hero || (s.featured[0] || null);
  const heroImg = hero ? hero.large : "";
  const title = s.settings.site_title || "PF";
  const parts = title.split(/\s*[—–-]\s*/);
  const t1 = parts[0] || title;
  const t2 = parts[1] || "";
  const firstName = t1.trim();
  const aboutPars = (s.settings.about_text || "")
    .split(/\n{2,}|\n/)
    .map((t) => t.trim())
    .filter(Boolean);
  const aboutHtml = aboutPars.length
    ? aboutPars.map((p, i) => `<p${i === 0 ? ' class="lead"' : ""}>${esc(p)}</p>`).join("")
    : `<p class="lead">Tu pojawi się mój opis — uzupełnisz go w panelu (Ustawienia).</p>`;
  const featured = s.featured.slice(0, 6);
  const post = s.posts[0];
  const albums = s.albums.filter((a) => a.featured).concat(s.albums).slice(0, 3);
  const featCells = featured.map((p, i) => {
    const cls = ["fcell"];
    const sz = p.feat_size || (featured.length === 1 ? "full" : i === 0 || i === 1 ? "wide" : i === 5 ? "full" : "std");
    cls.push(sz);
    return `<a class="${cls.join(" ")}" href="/portfolio/${p.album_slug}" data-link data-reveal="scale" data-cursor>
      ${pic(p.large_webp, p.large, p.title, dims(p) + `loading="lazy" decoding="async"`)}
      <span class="fcap">${esc(p.title || "kadr")}</span></a>`;
  }).join("");
  return `
  <section class="hero">
    <div class="hero-media">${heroImg ? `<img src="${heroImg}" alt="hero" fetchpriority="high">` : ""}</div>
    <div class="hero-top"><div class="wrap" style="display:flex;justify-content:space-between">
      <span class="label intro">${esc(s.settings.tagline || "Światło. Kadr.")}</span>
      <span class="label intro" style="display:none">EST. 2026</span>
    </div></div>
    <div class="hero-inner wrap">
      <h1 class="hero-title" aria-label="${esc(title)}">
        <span class="line">${esc(t1)}</span>
        ${t2 ? `<span class="line">${esc(t2)}</span>` : ""}
      </h1>
      <div class="hero-sub">
        <p class="tagline intro-2">${esc(s.settings.tagline || "")}</p>
        <a class="btn intro-2" href="/portfolio" data-link>Zobacz prace</a>
      </div>
      <div class="hero-meta-row intro-3">
        <span>${plCount(s.stats.photos, "kadr", "kadry", "kadrów")} w archiwum</span>
        <span>${plCount(s.stats.albums, "album", "albumy", "albumów")} / ${plCount(s.stats.posts, "wpis", "wpisy", "wpisów")}</span>
        <span class="hero-scroll">Przewiń<span class="tick"></span></span>
      </div>
    </div>
  </section>

  <div class="marquee hairline-t hairline-b" aria-hidden="true">
    <div class="marquee-track"><span>Światło</span><span>Kadr</span><span>Czerń</span><span>Biel</span><span>Fotografia</span><span>Kontrast</span><span>Ziarno</span><span>Cień</span></div>
  </div>

  <section class="sec" id="about">
    <div class="wrap">
      <div class="sec-head">
        <span class="label" data-reveal="up">Sekcja 01</span>
        <h2 class="h-display" data-reveal="up">${esc(s.settings.about_title || "O mnie")}</h2>
      </div>
      <div class="about-lead" data-reveal="up">
        ${aboutHtml}
      </div>
      <div class="about-foot" data-reveal="up">
        <span class="about-sign">— ${esc(firstName)}</span>
        <div class="about-cta">
          <a class="btn btn-dark" href="/portfolio" data-link>Portfolio</a>
          <a class="btn btn-dark" href="/kontakt" data-link>Kontakt</a>
        </div>
      </div>
      <div class="stats-row" data-stagger style="margin-top:3rem">
        <div class="stat"><div class="num" data-count="${s.stats.albums}" data-reveal="up">0</div><div class="cap">Albumy</div></div>
        <div class="stat"><div class="num" data-count="${s.stats.photos}" data-reveal="up">0</div><div class="cap">Zdjęcia</div></div>
        <div class="stat"><div class="num" data-count="${s.stats.posts}" data-reveal="up">0</div><div class="cap">Wpisy</div></div>
      </div>
    </div>
  </section>

  ${featured.length ? `
  <section class="sec" data-stagger data-reveal-group>
    <div class="wrap">
      <div class="sec-head">
        <span class="label" data-reveal="up">Sekcja 02</span>
        <h2 class="h-display" data-reveal="up">Wybrane<br>prace</h2>
        <a class="btn" href="/portfolio" data-link data-reveal="up">Wszystkie</a>
      </div>
      <div class="feature-grid">${featCells}</div>
    </div>
  </section>` : ""}

  ${albums.length ? `
  <section class="sec" data-stagger>
    <div class="wrap">
      <div class="sec-head">
        <span class="label" data-reveal="up">Sekcja 03</span>
        <h2 class="h-display" data-reveal="up">Albumy</h2>
      </div>
      ${albums.map((a, i) => `
      <a class="album-row ${a.featured ? "feat " : ""}${i % 2 ? "flip" : ""}" href="/portfolio/${a.slug}" data-link data-reveal="up">
        <div class="album-cover">
          ${a.cover ? pic(a.cover.thumb_webp, a.cover.thumb, a.title, dims(a.cover) + `loading="lazy" decoding="async"`) : `<div style="width:100%;height:100%;display:flex;align-items:center;justify-content:center;color:#999;letter-spacing:.3em">BRAK ZDJĘĆ</div>`}
          <span class="idx">${String(i + 1).padStart(2, "0")}</span>
        </div>
        <div class="album-info">
          <span class="label">Album</span>
          <h3 class="h-big">${esc(a.title)}</h3>
          <p class="desc">${esc(a.description || "")}</p>
          <div class="album-meta">
            <span>${plCount(a.photo_count, "zdjęcie", "zdjęcia", "zdjęć")}</span>
            ${a.featured ? `<span class="feat-badge">Wyróżniony</span>` : ""}
          </div>
          <span class="album-arrow">→</span>
        </div>
      </a>`).join("")}
    </div>
  </section>` : ""}

  ${post ? `
  <section class="sec">
    <div class="wrap">
      <div class="sec-head">
        <span class="label" data-reveal="up">Sekcja 04</span>
        <h2 class="h-display" data-reveal="up">Blog</h2>
      </div>
      <a class="post-row" href="/blog/${post.slug}" data-link data-reveal="up">
        <span class="date">${fmtDate(post.created_at)}</span>
        <div><h3 class="h-big">${esc(post.title)}</h3>
          <p class="excerpt">${esc(post.excerpt || "")}</p>
          <div class="tags">${(post.tags || []).map((t) => `<span class="tag">${esc(t)}</span>`).join("")}</div>
        </div>
        <span class="arrow">→</span>
      </a>
      <div style="margin-top:2.5rem" data-reveal="up"><a class="btn" href="/blog" data-link>Wszystkie wpisy</a></div>
    </div>
  </section>` : ""}
  `;
}

async function renderPortfolio() {
  const albums = S.site.albums;
  return `
  <div class="wrap" style="padding-top:calc(76px + clamp(2.5rem,7vh,5rem))">
    <span class="label intro">Sekcja 02 / Archiwum</span>
    <h1 class="h-display intro-2" style="margin-top:1.2rem">Portfolio</h1>
    <div class="album-hero-meta intro-3">
      <span>Albumów: <span class="val">${albums.length}</span></span>
      <span>Zdjęć: <span class="val">${S.site.stats.photos}</span></span>
    </div>
  </div>
  <section class="sec" data-stagger style="padding-top:clamp(2rem,5vw,4rem)">
    <div class="wrap">
      ${albums.length ? albums.map((a, i) => `
      <a class="album-row ${a.featured ? "feat " : ""}${i % 2 ? "flip" : ""}" href="/portfolio/${a.slug}" data-link data-reveal="up">
        <div class="album-cover">
          ${a.cover ? pic(a.cover.thumb_webp, a.cover.thumb, a.title, dims(a.cover) + `loading="lazy" decoding="async"`) : ""}
          <span class="idx">${String(i + 1).padStart(2, "0")}</span>
        </div>
        <div class="album-info">
          <span class="label">Album ${String(i + 1).padStart(2, "0")}</span>
          <h3 class="h-big">${esc(a.title)}</h3>
          <p class="desc">${esc(a.description || "")}</p>
          <div class="album-meta">
            <span>${plCount(a.photo_count, "zdjęcie", "zdjęcia", "zdjęć")}</span>
            ${a.featured ? `<span class="feat-badge">Wyróżniony</span>` : ""}
          </div>
          <span class="album-arrow">→</span>
        </div>
      </a>`).join("") : `
      <div class="label" data-reveal="up">Brak albumów. Dodaj pierwszy w panelu.</div>`}
    </div>
  </section>`;
}

async function renderAlbum(slug) {
  let data;
  try { data = await api("/api/albums/" + slug); }
  catch { return render404("/portfolio/" + slug); }
  const { album, photos } = data;
  window.__albumPhotos = photos;
  document.title = album.title + " — PF";
  const firstDate = photos[0] && photos[0].taken_at ? fmtDate(photos[0].taken_at) : fmtDate(album.created_at);
  return `
  <div class="wrap album-hero">
    <span class="label intro">Album / ${esc(album.title)}</span>
    <h1 class="h-display intro-2" style="margin-top:1.2rem">${esc(album.title)}</h1>
    <p class="about-text intro-3" style="max-width:70ch;margin-top:1.6rem">${esc(album.description || "")}</p>
    <div class="album-hero-meta intro-3">
      <span>Zdjęć: <span class="val">${album.photo_count}</span></span>
      <span>Data: <span class="val">${firstDate}</span></span>
      <span><a class="link-u" href="/portfolio" data-link>← Wszystkie albumy</a></span>
    </div>
  </div>
  <section class="sec" style="padding-top:0">
    <div class="wrap">
      <div class="masonry" data-stagger>
        ${photos.map((p, i) => `
        <figure class="mcell" data-reveal="up" data-cursor data-lb="${i}">
          ${pic(p.thumb_webp, p.thumb, p.title || "zdjęcie", dims(p) + `loading="${i < 6 ? "eager" : "lazy"}" decoding="async"`)}
          ${p.title || p.description ? `<figcaption class="mcap">${esc(p.title || "")}${p.description ? `<span class="sub">${esc(p.description)}</span>` : ""}</figcaption>` : ""}
        </figure>`).join("")}
      </div>
    </div>
  </section>`;
}

async function renderBlog() {
  let data;
  try { data = await api("/api/posts"); } catch { data = { posts: [] }; }
  const posts = data.posts;
  return `
  <div class="wrap" style="padding-top:calc(76px + clamp(2.5rem,7vh,5rem))">
    <span class="label intro">Sekcja 03 / Notatki</span>
    <h1 class="h-display intro-2" style="margin-top:1.2rem">Blog</h1>
  </div>
  <section class="sec" data-stagger style="padding-top:clamp(2rem,5vw,4rem)">
    <div class="wrap">
      ${posts.length ? posts.map((p) => `
      <a class="post-row" href="/blog/${p.slug}" data-link data-reveal="up">
        <span class="date">${fmtDate(p.created_at)}</span>
        <div>
          <h3 class="h-big">${esc(p.title)}</h3>
          <p class="excerpt">${esc(p.excerpt || "")}</p>
          <div class="tags">${(p.tags || []).map((t) => `<span class="tag">${esc(t)}</span>`).join("")}</div>
        </div>
        <span class="arrow">→</span>
      </a>`).join("") : `<div class="label" data-reveal="up">Brak wpisów. Napisz pierwszy w panelu.</div>`}
    </div>
  </section>`;
}

async function renderPost(slug) {
  let data;
  try { data = await api("/api/posts/" + slug); } catch { return render404("/blog/" + slug); }
  const p = data.post;
  document.title = p.title + " — PF";
  return `
  <div class="wrap post-hero">
    <span class="label intro">Blog / ${fmtDate(p.created_at)}</span>
    <h1 class="h-display intro-2" style="margin-top:1.2rem;max-width:18ch">${esc(p.title)}</h1>
    <div class="album-hero-meta intro-3">
      <span><a class="link-u" href="/blog" data-link>← Wszystkie wpisy</a></span>
      <div class="tags">${(p.tags || []).map((t) => `<span class="tag">${esc(t)}</span>`).join("")}</div>
    </div>
    ${p.cover ? `<div class="post-cover intro-3"><img src="${p.cover.large}" alt="${esc(p.title)}"></div>` : ""}
  </div>
  <article class="wrap">
    <div class="prose intro-3">${md(p.content)}</div>
  </article>`;
}

async function renderKontakt() {
  const s = S.site.settings;
  const row = (k, v) => v ? `<div class="ci-row"><span class="k">${k}</span><span class="v">${esc(v)}</span></div>` : "";
  return `
  <div class="wrap" style="padding-top:calc(76px + clamp(2.5rem,7vh,5rem))">
    <span class="label intro">Sekcja 04 / Napisz</span>
    <h1 class="h-display intro-2" style="margin-top:1.2rem">Kontakt</h1>
  </div>
  <section class="sec" style="padding-top:clamp(2rem,5vw,4rem)">
    <div class="wrap contact-grid">
      <form id="contact-form" data-reveal="up" novalidate>
        <div class="field">
          <label for="c-name">Imię i nazwisko</label>
          <input id="c-name" name="name" type="text" maxlength="120" required>
          <span class="bar"></span>
        </div>
        <div class="field">
          <label for="c-email">E-mail</label>
          <input id="c-email" name="email" type="email" maxlength="200" required>
          <span class="bar"></span>
        </div>
        <div class="field">
          <label for="c-msg">Wiadomość</label>
          <textarea id="c-msg" name="message" maxlength="4000" required></textarea>
          <span class="bar"></span>
        </div>
        <input type="text" name="website" style="display:none" tabindex="-1" autocomplete="off">
        <button class="btn" type="submit">Wyślij</button>
      </form>
      <div class="form-success" id="form-success">
        <div class="big">Dziękuję!</div>
        <p style="margin-top:1.2em;color:var(--muted)">Twoja wiadomość dotarła — odpowiem zwykle w ciągu 24 godzin.</p>
        <div style="margin-top:2rem;display:flex;gap:1rem;flex-wrap:wrap;justify-content:center">
          <a class="btn" href="/portfolio" data-link>Zobacz portfolio</a>
          <a class="btn" href="/" data-link style="border-color:var(--line);color:var(--muted)">Wróć na start</a>
        </div>
      </div>
      <div class="contact-info" data-reveal="up">
        <span class="label">Dane</span>
        ${row("E-mail", s.contact_email)}
        ${row("Telefon", s.contact_phone)}
        ${s.contact_instagram ? `<div class="ci-row"><span class="k">Instagram</span><span class="v">@${esc(s.contact_instagram.replace(/^@/, ""))}</span></div>` : ""}
      </div>
    </div>
  </section>`;
}

async function render404() {
  document.title = "404 — PF";
  return `
  <div class="wrap notfound">
    <span class="label">Błąd / Nie znaleziono</span>
    <div class="giant">404</div>
    <p style="margin-top:2rem;font-size:var(--fs-h3);text-transform:uppercase;letter-spacing:.1em">Tego kadru tu nie ma.</p>
    <a class="btn" href="/" data-link style="margin-top:2.5rem">Wróć na start</a>
  </div>`;
}

/* ------------------------------------------------------- admin -- */
let adminActive = false;
function renderAdmin() {
  adminActive = true;
  return '<div id="admin-root"></div>';
}

async function mountAdmin() {
  const root = $("#admin-root");
  if (!root) return;
  try {
    if (window.PFAdmin) await window.PFAdmin.mount(root);
  } catch (e) {
    root.innerHTML = `<div class="wrap" style="padding-top:120px"><span class="label">${esc(e.message)}</span></div>`;
  }
}

/* --------------------------------------------------- footer fill -- */
function fillFooter(site) {
  const s = site.settings;
  $("#nav-brand").textContent = (s.site_title || "PF").split(/[—–-]/)[0].trim();
  $("#nav-brand-sub").textContent = "FOTO";
  document.title = s.site_title + " — Fotografia";
  $("#f-email").textContent = s.contact_email || "—";
  $("#f-phone").textContent = s.contact_phone || "—";
  $("#f-ig").textContent = s.contact_instagram ? "@" + s.contact_instagram.replace(/^@/, "") : "—";
  $("#f-text").textContent = s.footer_text || "—";
  $("#f-copy").textContent = "© " + new Date().getFullYear() + " " + (s.site_title || "PF");
}

/* ------------------------------------------------------- boot -- */
async function boot() {
  initHeader();
  initCursor();
  initSearch();
  initLightbox();
  document.addEventListener("click", (e) => {
    const m = e.target.closest("[data-lb]");
    if (m) {
      const photos = window.__albumPhotos || [];
      const idx = Number(m.dataset.lb);
      if (photos.length) openLightbox(photos, idx);
    }
  });
  runPreloader(async () => {
    try { S.site = await api("/api/site"); }
    catch (e) { toast("Nie mogę połączyć się z serwerem: " + e.message, "err"); }
    fillFooter(S.site);
    await render(S.path);
    $("#preloader")?.remove();
  });
}

/* albumy: lista zdjęć dla lightboxa (ustawiana w renderAlbum) */
window.__albumPhotos = [];
window.PF = { api, esc, toast, md, fmtDate, plCount, navigate, toast };
window.PF.initReveals = initReveals;
window.PF.buildMarquees = buildMarquees;
window.PF.initContactForm = initContactForm;
window.PF.openLightbox = openLightbox;
window.PF.countUp = countUp;

boot();

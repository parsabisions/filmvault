/**
 * FilmVault — Application Logic
 *
 * No frameworks. No build step. Just clean vanilla JS.
 * Features: search, filters, infinite scroll, detail panel, favorites, keyboard shortcuts.
 */

// ── Palette for poster fallbacks ─────────────────────
const PALETTES = [
  ['#1a1520', '#8b5cf6'],
  ['#151a1c', '#06b6d4'],
  ['#1a1715', '#f59e0b'],
  ['#151a15', '#10b981'],
  ['#1a1518', '#ec4899'],
  ['#15161a', '#6366f1'],
  ['#1a1815', '#f97316'],
  ['#17151a', '#a855f7'],
];

// ── State ────────────────────────────────────────────
let allFilms = [];
let filtered = [];
let favorites = new Set();
let currentFilter = 'all';
let currentGenre = '';
let currentYear = '';
let currentSort = 'title';
let searchQuery = '';
let renderedCount = 0;
const BATCH = 80;

// ── DOM refs ─────────────────────────────────────────
const $ = (s) => document.querySelector(s);
const $$ = (s) => document.querySelectorAll(s);

const grid = $('#grid');
const search = $('#search');
const countNum = $('#count-num');
const totalNum = $('#total-num');
const panel = $('#panel');
const overlay = $('#overlay');
const empty = $('#empty');
const sentinel = $('#sentinel');
const loader = $('#loader');
const app = $('#app');
const genreFilter = $('#genre-filter');
const yearFilter = $('#year-filter');
const sortFilter = $('#sort-filter');

// ── Init ─────────────────────────────────────────────
async function init() {
  loadState();

  try {
    const res = await fetch('catalog.json');
    if (!res.ok) throw new Error('Failed to load catalog');
    allFilms = await res.json();
  } catch (err) {
    loader.innerHTML = '<p class="loader-text" style="color:var(--err)">Failed to load library</p>';
    return;
  }

  totalNum.textContent = allFilms.length.toLocaleString();
  populateGenreFilter();
  applyFilters();

  loader.classList.add('hidden');
  app.classList.remove('is-hidden');
  setupObserver();
}

// ── State persistence (localStorage) ─────────────────
function loadState() {
  try {
    favorites = new Set(JSON.parse(localStorage.getItem('fv_favs') || '[]'));
  } catch {
    favorites = new Set();
  }
}

function saveFavs() {
  localStorage.setItem('fv_favs', JSON.stringify([...favorites]));
}

// ── Genre filter population ──────────────────────────
function populateGenreFilter() {
  const genres = new Set();
  for (let i = 0; i < allFilms.length; i++) {
    const g = allFilms[i].genre;
    if (g) genres.add(g);
  }
  const sorted = [...genres].sort();
  const frag = document.createDocumentFragment();
  sorted.forEach((g) => {
    const opt = document.createElement('option');
    opt.value = g;
    opt.textContent = g;
    frag.appendChild(opt);
  });
  genreFilter.appendChild(frag);
}

// ── Filters ──────────────────────────────────────────
function applyFilters() {
  const q = searchQuery.toLowerCase();

  filtered = allFilms.filter((film, idx) => {
    // Status filter
    if (currentFilter === 'available' && !film.available) return false;
    if (currentFilter === 'missing' && film.available) return false;
    if (currentFilter === 'favorites' && !favorites.has(idx)) return false;

    // Genre filter
    if (currentGenre && film.genre !== currentGenre) return false;

    // Year filter
    if (currentYear) {
      const y = parseInt(film.year) || 0;
      if (currentYear === '2020s' && y < 2020) return false;
      if (currentYear === '2010s' && (y < 2010 || y >= 2020)) return false;
      if (currentYear === '2000s' && (y < 2000 || y >= 2010)) return false;
      if (currentYear === '1990s' && (y < 1990 || y >= 2000)) return false;
      if (currentYear === 'older' && y >= 1990) return false;
    }

    // Search
    if (q) {
      if (film.title.toLowerCase().indexOf(q) === -1) return false;
    }

    return true;
  });

  sortFiltered();
  renderedCount = 0;
  grid.innerHTML = '';
  countNum.textContent = filtered.length.toLocaleString();

  if (filtered.length === 0) {
    empty.classList.remove('is-hidden');
    sentinel.classList.add('is-hidden');
  } else {
    empty.classList.add('is-hidden');
    sentinel.classList.remove('is-hidden');
    renderBatch();
  }
}

function sortFiltered() {
  filtered.sort((a, b) => {
    switch (currentSort) {
      case 'title':
        return a.title.localeCompare(b.title);
      case 'title_desc':
        return b.title.localeCompare(a.title);
      case 'year_desc':
        return (parseInt(b.year) || 0) - (parseInt(a.year) || 0);
      case 'year':
        return (parseInt(a.year) || 0) - (parseInt(b.year) || 0);
      case 'rating':
        return (parseFloat(b.rating) || 0) - (parseFloat(a.rating) || 0);
      default:
        return 0;
    }
  });
}

// ── Rendering ────────────────────────────────────────
function renderBatch() {
  const frag = document.createDocumentFragment();
  const end = Math.min(renderedCount + BATCH, filtered.length);

  for (let i = renderedCount; i < end; i++) {
    frag.appendChild(createCard(filtered[i], allFilms.indexOf(filtered[i])));
  }

  grid.appendChild(frag);
  renderedCount = end;
}

function createCard(film, globalIdx) {
  const words = film.title.split(/\s+/);
  const initials =
    words.length >= 2
      ? (words[0][0] + words[1][0]).toUpperCase()
      : film.title.substring(0, 2).toUpperCase();
  const palette = hashPalette(film.title);
  const bg = palette[0];
  const fg = palette[1];
  const isFav = favorites.has(globalIdx);

  const article = document.createElement('article');
  article.className = 'card';
  article.tabIndex = 0;
  article.setAttribute('role', 'listitem');
  article.dataset.idx = globalIdx;
  article.dataset.bg = bg;
  article.dataset.fg = fg;
  article.dataset.initials = initials;

  const favClass = isFav ? ' is-active' : '';
  const favFill = isFav ? 'currentColor' : 'none';

  let posterHtml;
  if (film.poster) {
    posterHtml =
      '<img src="' +
      escHtml(film.poster) +
      '" alt="" loading="lazy" class="poster-img" decoding="async">';
  } else {
    posterHtml =
      '<div class="poster-fallback" style="background:' +
      bg +
      '"><span style="color:' +
      fg +
      '">' +
      escHtml(initials) +
      '</span></div>';
  }

  article.innerHTML =
    '<button class="fav-toggle' +
    favClass +
    '" data-idx="' +
    globalIdx +
    '" aria-label="Toggle favorite">' +
    '<svg viewBox="0 0 24 24" width="16" height="16" fill="' +
    favFill +
    '" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">' +
    '<path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78a5.5 5.5 0 0 0 0-7.78z"/>' +
    '</svg></button>' +
    '<div class="poster-wrap" style="background:' +
    bg +
    '">' +
    posterHtml +
    '</div>' +
    '<div class="card-body">' +
    '<h3 class="card-title">' +
    escHtml(film.title) +
    '</h3>' +
    '<div class="card-meta">' +
    '<span>' +
    escHtml(film.year || '—') +
    '</span>' +
    (film.rating ? '<span>★ ' + escHtml(film.rating) + '</span>' : '') +
    '<span class="status-dot ' +
    (film.available ? 'dot-ok' : 'dot-err') +
    '"></span>' +
    '</div></div>';

  return article;
}

// ── Infinite scroll ──────────────────────────────────
function setupObserver() {
  if (!('IntersectionObserver' in window)) {
    // Fallback: just render everything
    while (renderedCount < filtered.length) renderBatch();
    return;
  }
  const obs = new IntersectionObserver(
    (entries) => {
      if (entries[0].isIntersecting && renderedCount < filtered.length) {
        renderBatch();
      }
    },
    { rootMargin: '300px' }
  );
  obs.observe(sentinel);
}

// ── Detail panel ─────────────────────────────────────
function openDetail(globalIdx) {
  const film = allFilms[globalIdx];
  if (!film) return;

  const palette = hashPalette(film.title);
  const bg = palette[0];
  const fg = palette[1];
  const words = film.title.split(/\s+/);
  const initials =
    words.length >= 2
      ? (words[0][0] + words[1][0]).toUpperCase()
      : film.title.substring(0, 2).toUpperCase();

  let posterDetail;
  if (film.poster) {
    posterDetail =
      '<img src="' + escHtml(film.poster) + '" alt="' + escHtml(film.title) + '">';
  } else {
    posterDetail =
      '<div class="poster-fallback" style="background:' +
      bg +
      ';min-height:160px"><span style="color:' +
      fg +
      '">' +
      escHtml(initials) +
      '</span></div>';
  }

  let downloadsHtml = '';
  if (film.links && film.links.length > 0) {
    downloadsHtml = film.links
      .map(function (link) {
        const filename = link[0].split('/').pop();
        return (
          '<div class="dl-row">' +
          '<div class="dl-info">' +
          '<span class="dl-filename">' + escHtml(filename) + '</span>' +
          '<span class="dl-meta">' + escHtml(link[1]) + ' · ' + escHtml(link[2]) + '</span>' +
          '</div>' +
          '<div class="dl-actions">' +
          '<button class="copy-btn" data-url="' + escHtml(link[0]) + '">' +
          '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">' +
          '<rect x="9" y="9" width="13" height="13" rx="2"/>' +
          '<path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>' +
          '</svg> Copy</button>' +
          '<a href="' + escHtml(link[0]) + '" target="_blank" rel="noopener" class="dl-btn">Download</a>' +
          '</div></div>'
        );
      })
      .join('');
  } else {
    downloadsHtml = '<p style="font-size:12px;color:var(--text-3);padding:8px 0">No downloads available</p>';
  }

  const metaParts = [];
  if (film.year) metaParts.push('<span>' + escHtml(film.year) + '</span>');
  if (film.rating) metaParts.push('<span>★ ' + escHtml(film.rating) + '</span>');
  if (film.genre) metaParts.push('<span>' + escHtml(film.genre) + '</span>');
  metaParts.push(
    '<span class="' + (film.available ? 'status-ok' : 'status-err') + '">' +
    (film.available ? 'Available' : 'Missing') +
    '</span>'
  );

  const isFav = favorites.has(globalIdx);
  const favText = isFav ? 'Favorited' : 'Favorite';

  const panelContent = $('#panel-content');
  panelContent.innerHTML =
    '<div class="panel-top">' +
    '<button class="panel-close" aria-label="Close detail">' +
    '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">' +
    '<path d="M18 6L6 18M6 6l12 12"/>' +
    '</svg></button></div>' +
    '<div class="panel-poster" style="background:' + bg + '">' + posterDetail + '</div>' +
    '<div class="panel-body">' +
    '<h2 class="panel-title">' + escHtml(film.title) + '</h2>' +
    '<div class="panel-meta">' + metaParts.join('') + '</div>' +
    '<div class="panel-dl"><h3>Downloads</h3>' + downloadsHtml + '</div>' +
    '<button class="fav-btn' + (isFav ? ' is-active' : '') + '" data-idx="' + globalIdx + '">' +
    '<svg viewBox="0 0 24 24" width="16" height="16" fill="' + (isFav ? 'currentColor' : 'none') + '" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">' +
    '<path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78a5.5 5.5 0 0 0 0-7.78z"/>' +
    '</svg> ' + favText + '</button>' +
    '</div>';

  overlay.classList.add('is-open');
  panel.classList.add('is-open');
  overlay.setAttribute('aria-hidden', 'false');
  panel.setAttribute('aria-hidden', 'false');
  document.body.style.overflow = 'hidden';
}

function closeDetail() {
  overlay.classList.remove('is-open');
  panel.classList.remove('is-open');
  overlay.setAttribute('aria-hidden', 'true');
  panel.setAttribute('aria-hidden', 'true');
  document.body.style.overflow = '';
}

// ── Favorites ────────────────────────────────────────
function toggleFavorite(idx) {
  if (favorites.has(idx)) {
    favorites.delete(idx);
  } else {
    favorites.add(idx);
  }
  saveFavs();

  // Update all visible elements with this idx
  $$('.fav-toggle[data-idx="' + idx + '"]').forEach(function (btn) {
    const active = favorites.has(idx);
    btn.classList.toggle('is-active', active);
    btn.querySelector('svg').setAttribute('fill', active ? 'currentColor' : 'none');
  });

  $$('.fav-btn[data-idx="' + idx + '"]').forEach(function (btn) {
    const active = favorites.has(idx);
    btn.classList.toggle('is-active', active);
    btn.querySelector('svg').setAttribute('fill', active ? 'currentColor' : 'none');
    btn.childNodes[btn.childNodes.length - 1].textContent = active ? ' Favorited' : ' Favorite';
  });

  if (currentFilter === 'favorites') applyFilters();
}

// ── Utilities ────────────────────────────────────────
function hashPalette(str) {
  let h = 0;
  for (let i = 0; i < str.length; i++) {
    h = ((h << 5) - h + str.charCodeAt(i)) | 0;
  }
  return PALETTES[Math.abs(h) % PALETTES.length];
}

function escHtml(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

// ── Event listeners ──────────────────────────────────

// Grid: click card → detail, click heart → favorite
grid.addEventListener('click', function (e) {
  const favBtn = e.target.closest('.fav-toggle');
  if (favBtn) {
    e.stopPropagation();
    toggleFavorite(parseInt(favBtn.dataset.idx));
    return;
  }
  const card = e.target.closest('.card');
  if (card) openDetail(parseInt(card.dataset.idx));
});

// Grid: Enter key opens detail
grid.addEventListener('keydown', function (e) {
  if (e.key === 'Enter') {
    const card = e.target.closest('.card');
    if (card) openDetail(parseInt(card.dataset.idx));
  }
});

// Image error → show fallback
grid.addEventListener(
  'error',
  function (e) {
    if (e.target.tagName === 'IMG' && e.target.classList.contains('poster-img')) {
      const wrap = e.target.closest('.poster-wrap');
      const card = e.target.closest('.card');
      if (wrap && card) {
        e.target.remove();
        const div = document.createElement('div');
        div.className = 'poster-fallback';
        div.style.background = card.dataset.bg;
        div.innerHTML = '<span style="color:' + card.dataset.fg + '">' + escHtml(card.dataset.initials) + '</span>';
        wrap.appendChild(div);
      }
    }
  },
  true
);

// Search
let searchTimer;
search.addEventListener('input', function () {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(function () {
    searchQuery = search.value.trim();
    applyFilters();
  }, 150);
});

// Filter chips
$$('.chip').forEach(function (chip) {
  chip.addEventListener('click', function () {
    $$('.chip').forEach(function (c) {
      c.classList.remove('is-active');
    });
    chip.classList.add('is-active');
    currentFilter = chip.dataset.filter;
    applyFilters();
  });
});

// Dropdowns
genreFilter.addEventListener('change', function (e) {
  currentGenre = e.target.value;
  applyFilters();
});
yearFilter.addEventListener('change', function (e) {
  currentYear = e.target.value;
  applyFilters();
});
sortFilter.addEventListener('change', function (e) {
  currentSort = e.target.value;
  applyFilters();
});

// Detail panel close
overlay.addEventListener('click', closeDetail);
panel.addEventListener('click', function (e) {
  if (e.target.closest('.panel-close')) closeDetail();
});

// Favorite button in panel (delegated)
panel.addEventListener('click', function (e) {
  const favBtn = e.target.closest('.fav-btn');
  if (favBtn) {
    toggleFavorite(parseInt(favBtn.dataset.idx));
  }
});

// Copy to clipboard (delegated on document)
document.addEventListener('click', function (e) {
  const copyBtn = e.target.closest('.copy-btn');
  if (!copyBtn) return;

  const url = copyBtn.dataset.url;
  if (!url) return;

  if (navigator.clipboard && navigator.clipboard.writeText) {
    navigator.clipboard.writeText(url).then(function () {
      showCopied(copyBtn);
    });
  } else {
    // Fallback
    const ta = document.createElement('textarea');
    ta.value = url;
    ta.style.cssText = 'position:fixed;left:-9999px';
    document.body.appendChild(ta);
    ta.select();
    document.execCommand('copy');
    document.body.removeChild(ta);
    showCopied(copyBtn);
  }
});

function showCopied(btn) {
  btn.classList.add('copied');
  var originalHtml = btn.innerHTML;
  btn.innerHTML =
    '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6L9 17l-5-5"/></svg> Copied';
  setTimeout(function () {
    btn.classList.remove('copied');
    btn.innerHTML = originalHtml;
  }, 2000);
}

// Keyboard shortcuts
document.addEventListener('keydown', function (e) {
  // / → focus search
  if (e.key === '/' && document.activeElement !== search && !e.ctrlKey && !e.metaKey) {
    e.preventDefault();
    search.focus();
  }

  // Escape → close panel or blur search
  if (e.key === 'Escape') {
    if (panel.classList.contains('is-open')) {
      closeDetail();
    } else if (document.activeElement === search) {
      search.blur();
      if (search.value) {
        search.value = '';
        searchQuery = '';
        applyFilters();
      }
    }
  }
});

// ── Start ────────────────────────────────────────────
init();

/**
 * FilmVault — Application Logic
 *
 * No frameworks. No build step. Clean vanilla JS.
 * Search, filters, infinite scroll, detail panel, favorites,
 * video player with quality selector, keyboard shortcuts.
 */

// ── Palette for poster fallbacks ─────────────────────
const PALETTES = [
  ['#1a1520', '#8b5cf6'], ['#151a1c', '#06b6d4'],
  ['#1a1715', '#f59e0b'], ['#151a15', '#10b981'],
  ['#1a1518', '#ec4899'], ['#15161a', '#6366f1'],
  ['#1a1815', '#f97316'], ['#17151a', '#a855f7'],
];

// ── State ────────────────────────────────────────────
let allFilms = [], filtered = [], favorites = new Set(), edits = {};
let currentFilter = 'all', currentGenre = '', currentYear = '', currentSort = 'title', searchQuery = '';
let renderedCount = 0;
const BATCH = 80;

// ── DOM refs ─────────────────────────────────────────
const $ = s => document.querySelector(s);
const $$ = s => document.querySelectorAll(s);
const grid = $('#grid'), search = $('#search'), countNum = $('#count-num'), totalNum = $('#total-num');
const panel = $('#panel'), overlay = $('#overlay'), empty = $('#empty'), sentinel = $('#sentinel');
const loader = $('#loader'), app = $('#app');
const genreFilter = $('#genre-filter'), yearFilter = $('#year-filter'), sortFilter = $('#sort-filter');
const playerModal = $('#player-modal'), playerVideo = $('#player-video'), playerTitle = $('#player-title');
const playerQuality = $('#player-quality'), playerPlay = $('#player-play');
const iconPlay = $('#icon-play'), iconPause = $('#icon-pause');
const playerTime = $('#player-time'), playerSeek = $('#player-seek');
const playerVol = $('#player-vol'), playerFullscreen = $('#player-fullscreen');
const playerBack = $('#player-back'), playerLoading = $('#player-loading');

// ── Link helpers (support both [url,q,type] and {url,quality,type}) ──
function lnkUrl(l) { return l.url || (l[0] || ''); }
function lnkQ(l)   { return l.quality || (l[1] || ''); }
function lnkType(l){ return l.type || (l[2] || 'original'); }

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

// ── State persistence ────────────────────────────────
function loadState() {
  try { favorites = new Set(JSON.parse(localStorage.getItem('fv_favs') || '[]')); } catch { favorites = new Set(); }
  try { edits = JSON.parse(localStorage.getItem('fv_edits') || '{}'); } catch { edits = {}; }
}
function saveFavs() { localStorage.setItem('fv_favs', JSON.stringify([...favorites])); }
function saveEdits() { localStorage.setItem('fv_edits', JSON.stringify(edits)); }
function applyEdits(film, idx) {
  var e = edits[idx];
  if (!e) return film;
  return Object.assign({}, film, { title: e.title || film.title, year: e.year || film.year, rating: e.rating || film.rating, genre: e.genre || film.genre });
}

// ── Genre filter population ──────────────────────────
function populateGenreFilter() {
  const genres = new Set();
  for (let i = 0; i < allFilms.length; i++) { const g = allFilms[i].genre; if (g) genres.add(g); }
  const frag = document.createDocumentFragment();
  [...genres].sort().forEach(g => {
    const opt = document.createElement('option');
    opt.value = g; opt.textContent = g;
    frag.appendChild(opt);
  });
  genreFilter.appendChild(frag);
}

// ── Filters ──────────────────────────────────────────
function applyFilters() {
  const q = searchQuery.toLowerCase();
  filtered = allFilms.filter((film, idx) => {
    if (currentFilter === 'available' && !film.available) return false;
    if (currentFilter === 'missing' && film.available) return false;
    if (currentFilter === 'favorites' && !favorites.has(idx)) return false;
    if (currentGenre && film.genre !== currentGenre) return false;
    if (currentYear) {
      const y = parseInt(film.year) || 0;
      if (currentYear === '2020s' && y < 2020) return false;
      if (currentYear === '2010s' && (y < 2010 || y >= 2020)) return false;
      if (currentYear === '2000s' && (y < 2000 || y >= 2010)) return false;
      if (currentYear === '1990s' && (y < 1990 || y >= 2000)) return false;
      if (currentYear === 'older' && y >= 1990) return false;
    }
    if (q && film.title.toLowerCase().indexOf(q) === -1) return false;
    return true;
  });
  sortFiltered();
  renderedCount = 0;
  grid.innerHTML = '';
  countNum.textContent = filtered.length.toLocaleString();
  if (filtered.length === 0) { empty.classList.remove('is-hidden'); sentinel.classList.add('is-hidden'); }
  else { empty.classList.add('is-hidden'); sentinel.classList.remove('is-hidden'); renderBatch(); }
}

function sortFiltered() {
  filtered.sort((a, b) => {
    switch (currentSort) {
      case 'title': return a.title.localeCompare(b.title);
      case 'title_desc': return b.title.localeCompare(a.title);
      case 'year_desc': return (parseInt(b.year) || 0) - (parseInt(a.year) || 0);
      case 'year': return (parseInt(a.year) || 0) - (parseInt(b.year) || 0);
      case 'rating': return (parseFloat(b.rating) || 0) - (parseFloat(a.rating) || 0);
      default: return 0;
    }
  });
}

// ── Rendering ────────────────────────────────────────
function renderBatch() {
  const frag = document.createDocumentFragment();
  const end = Math.min(renderedCount + BATCH, filtered.length);
  for (let i = renderedCount; i < end; i++) frag.appendChild(createCard(filtered[i], allFilms.indexOf(filtered[i])));
  grid.appendChild(frag);
  renderedCount = end;
}

function createCard(film, globalIdx) {
  const words = film.title.split(/\s+/);
  const initials = words.length >= 2 ? (words[0][0] + words[1][0]).toUpperCase() : film.title.substring(0, 2).toUpperCase();
  const palette = hashPalette(film.title);
  const [bg, fg] = palette;
  const isFav = favorites.has(globalIdx);
  const article = document.createElement('article');
  article.className = 'card'; article.tabIndex = 0;
  article.setAttribute('role', 'listitem'); article.dataset.idx = globalIdx;
  article.dataset.bg = bg; article.dataset.fg = fg; article.dataset.initials = initials;

  let posterHtml = film.poster
    ? '<img src="' + escHtml(film.poster) + '" alt="" loading="lazy" class="poster-img" decoding="async">'
    : '<div class="poster-fallback" style="background:' + bg + '"><span style="color:' + fg + '">' + escHtml(initials) + '</span></div>';

  const playHtml = (film.available && film.links && film.links.length > 0)
    ? '<button class="play-overlay" data-play="' + globalIdx + '" aria-label="Watch ' + escHtml(film.title) + '"><span class="play-circle"><svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><polygon points="6,3 20,12 6,21"/></svg></span></button>'
    : '';

  article.innerHTML =
    '<button class="fav-toggle' + (isFav ? ' is-active' : '') + '" data-idx="' + globalIdx + '" aria-label="Toggle favorite">' +
    '<svg viewBox="0 0 24 24" width="16" height="16" fill="' + (isFav ? 'currentColor' : 'none') +
    '" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78a5.5 5.5 0 0 0 0-7.78z"/></svg></button>' +
    '<div class="poster-wrap" style="background:' + bg + '">' + posterHtml + playHtml + '</div>' +
    '<div class="card-body"><h3 class="card-title">' + escHtml(film.title) + '</h3>' +
    '<div class="card-meta"><span>' + escHtml(film.year || '—') + '</span>' +
    (film.rating ? '<span>★ ' + escHtml(film.rating) + '</span>' : '') +
    '<span class="status-dot ' + (film.available ? 'dot-ok' : 'dot-err') + '"></span></div></div>';
  return article;
}

// ── Infinite scroll ──────────────────────────────────
function setupObserver() {
  if (!('IntersectionObserver' in window)) { while (renderedCount < filtered.length) renderBatch(); return; }
  new IntersectionObserver(entries => {
    if (entries[0].isIntersecting && renderedCount < filtered.length) renderBatch();
  }, { rootMargin: '300px' }).observe(sentinel);
}

// ── Detail panel ─────────────────────────────────────
function openDetail(globalIdx) {
  let film = allFilms[globalIdx];
  if (!film) return;
  film = applyEdits(film, globalIdx);
  const palette = hashPalette(film.title);
  const [bg, fg] = palette;
  const words = film.title.split(/\s+/);
  const initials = words.length >= 2 ? (words[0][0] + words[1][0]).toUpperCase() : film.title.substring(0, 2).toUpperCase();

  let posterDetail = film.poster
    ? '<img src="' + escHtml(film.poster) + '" alt="' + escHtml(film.title) + '">'
    : '<div class="poster-fallback" style="background:' + bg + ';min-height:160px"><span style="color:' + fg + '">' + escHtml(initials) + '</span></div>';

  // Separate video links from subtitles
  const allLinks = film.links || [];
  const videoLinks = allLinks.filter(l => lnkType(l) !== 'subtitle');
  const subLinks = allLinks.filter(l => lnkType(l) === 'subtitle');

  // Video download rows
  let downloadsHtml = videoLinks.length > 0
    ? videoLinks.map(link => {
        const url = lnkUrl(link), q = lnkQ(link), lt = lnkType(link);
        const fn = url.split('/').pop();
        const isVid = /\.(mp4|mkv|avi|mov|webm)$/i.test(url);
        let act = '<div class="dl-actions">' +
          '<button class="copy-btn" data-url="' + escHtml(url) + '"><svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg> Copy</button>';
        if (isVid) act += '<button class="watch-link-btn" data-play="' + globalIdx + '" data-url="' + escHtml(url) + '"><svg viewBox="0 0 24 24" width="13" height="13" fill="currentColor"><polygon points="6,3 20,12 6,21"/></svg> Watch</button>';
        else act += '<a href="' + escHtml(url) + '" target="_blank" rel="noopener" class="dl-btn">Download</a>';
        return '<div class="dl-row"><div class="dl-info"><span class="dl-filename">' + escHtml(fn) + '</span><span class="dl-meta">' + escHtml(q) + 'p · ' + escHtml(lt) + '</span></div>' + act + '</div>';
      }).join('')
    : '<p style="font-size:12px;color:var(--text-3);padding:8px 0">No downloads available</p>';

  // Subtitle rows
  let subsHtml = subLinks.length > 0
    ? '<h3 style="margin-top:24px">Subtitles (' + subLinks.length + ')</h3>' +
      subLinks.map(link => {
        const url = lnkUrl(link), fn = url.split('/').pop();
        const lang = /Farsi|Persian|IR/i.test(fn) ? 'Farsi' : /English|EN/i.test(fn) ? 'English' : 'Sub';
        return '<div class="dl-row"><div class="dl-info"><span class="dl-filename">' + escHtml(fn) + '</span><span class="dl-meta">' + lang + '</span></div>' +
          '<div class="dl-actions"><button class="copy-btn" data-url="' + escHtml(url) + '"><svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg> Copy</button>' +
          '<a href="' + escHtml(url) + '" target="_blank" rel="noopener" class="dl-btn">Download</a></div></div>';
      }).join('')
    : '';

  const metaParts = [];
  if (film.year) metaParts.push('<span>' + escHtml(film.year) + '</span>');
  if (film.rating) metaParts.push('<span>★ ' + escHtml(film.rating) + '</span>');
  if (film.genre) metaParts.push('<span>' + escHtml(film.genre) + '</span>');
  metaParts.push('<span class="' + (film.available ? 'status-ok' : 'status-err') + '">' + (film.available ? 'Available' : 'Missing') + '</span>');

  const isFav = favorites.has(globalIdx);
  const watchHtml = (film.available && videoLinks.length > 0)
    ? '<button class="watch-btn" data-play="' + globalIdx + '"><svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><polygon points="6,3 20,12 6,21"/></svg> Watch</button>'
    : '';

  $('#panel-content').innerHTML =
    '<div class="panel-top"><button class="panel-edit" data-edit="' + globalIdx + '">Edit</button><button class="panel-close" aria-label="Close detail"><svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6L6 18M6 6l12 12"/></svg></button></div>' +
    '<div class="panel-poster" style="background:' + bg + '">' + posterDetail + '</div>' +
    '<div class="panel-body"><h2 class="panel-title">' + escHtml(film.title) + '</h2>' +
    '<div class="panel-meta">' + metaParts.join('') + '</div>' + watchHtml +
    '<div class="panel-dl"><h3>Downloads</h3>' + downloadsHtml + subsHtml + '</div>' +
    '<button class="fav-btn' + (isFav ? ' is-active' : '') + '" data-idx="' + globalIdx + '">' +
    '<svg viewBox="0 0 24 24" width="16" height="16" fill="' + (isFav ? 'currentColor' : 'none') +
    '" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20.84 4.61a5.5 5.5 0 0 0-7.78 0L12 5.67l-1.06-1.06a5.5 5.5 0 0 0-7.78 7.78l1.06 1.06L12 21.23l7.78-7.78a5.5 5.5 0 0 0 0-7.78z"/></svg> ' + (isFav ? 'Favorited' : 'Favorite') + '</button>' +
    '<div class="edit-form" id="editForm">' +
    '<div class="edit-row"><label>Title</label><input class="edit-input" id="edTitle" type="text" value="' + escHtml(film.title) + '"></div>' +
    '<div class="edit-row"><label>Year</label><input class="edit-input" id="edYear" type="text" value="' + escHtml(film.year || '') + '"></div>' +
    '<div class="edit-row"><label>Rating</label><input class="edit-input" id="edRating" type="text" value="' + escHtml(film.rating || '') + '"></div>' +
    '<div class="edit-row"><label>Genre</label><input class="edit-input" id="edGenre" type="text" value="' + escHtml(film.genre || '') + '"></div>' +
    '<div class="edit-actions"><button class="edit-save" id="edSave">Save</button><button class="edit-cancel" id="edCancel">Cancel</button></div>' +
    '<div class="saved-msg" id="edMsg" style="display:none">Saved!</div>' +
    '</div></div>';

  overlay.classList.add('is-open');
  panel.classList.add('is-open');
  overlay.setAttribute('aria-hidden', 'false');
  panel.setAttribute('aria-hidden', 'false');
  document.body.style.overflow = 'hidden';
}

function closeDetail() {
  overlay.classList.remove('is-open'); panel.classList.remove('is-open');
  overlay.setAttribute('aria-hidden', 'true'); panel.setAttribute('aria-hidden', 'true');
  document.body.style.overflow = '';
}

// ── Video Player ─────────────────────────────────────
var currentFilm = null;

function openPlayer(globalIdx, specificUrl) {
  var film = allFilms[globalIdx];
  if (!film || !film.links || film.links.length === 0) return;
  currentFilm = film;

  // Build video source list
  var videoLinks = film.links.filter(function (l) {
    return /\.(mp4|mkv|webm|mov|avi)$/i.test(lnkUrl(l)) || lnkType(l) === 'original' || lnkType(l) === 'dubbed';
  });
  if (videoLinks.length === 0) return;

  // Populate quality selector
  playerQuality.innerHTML = '';
  var bestIdx = 0;
  videoLinks.forEach(function (link, i) {
    var opt = document.createElement('option');
    opt.value = i;
    opt.textContent = lnkQ(link) + 'p — ' + lnkType(link);
    if (specificUrl && lnkUrl(link) === specificUrl) bestIdx = i;
    if (!specificUrl && parseInt(lnkQ(link)) > parseInt(lnkQ(videoLinks[bestIdx]))) bestIdx = i;
    playerQuality.appendChild(opt);
  });
  playerQuality.value = bestIdx;

  loadVideoSource(lnkUrl(videoLinks[bestIdx]));
  playerTitle.textContent = film.title + (film.year ? ' (' + film.year + ')' : '');
  playerModal.classList.add('is-open');
  playerModal.setAttribute('aria-hidden', 'false');
  document.body.style.overflow = 'hidden';
}

function loadVideoSource(url) {
  playerLoading.setAttribute('aria-hidden', 'false');
  iconPlay.classList.add('hidden'); iconPause.classList.add('hidden');
  playerVideo.pause(); playerVideo.removeAttribute('src'); playerVideo.load();
  playerVideo.src = url; playerVideo.load();
}

function closePlayer() {
  playerVideo.pause(); playerVideo.removeAttribute('src'); playerVideo.load();
  playerModal.classList.remove('is-open'); playerModal.setAttribute('aria-hidden', 'true');
  currentFilm = null;
  if (!panel.classList.contains('is-open')) document.body.style.overflow = '';
}

function togglePlayPause() {
  if (playerVideo.paused) playerVideo.play().catch(function(){});
  else playerVideo.pause();
}

function formatTime(s) {
  if (!s || isNaN(s)) return '0:00';
  var h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), sec = Math.floor(s % 60);
  return h > 0 ? h + ':' + String(m).padStart(2, '0') + ':' + String(sec).padStart(2, '0')
               : m + ':' + String(sec).padStart(2, '0');
}

// ── Favorites ────────────────────────────────────────
function toggleFavorite(idx) {
  favorites.has(idx) ? favorites.delete(idx) : favorites.add(idx);
  saveFavs();
  $$('.fav-toggle[data-idx="' + idx + '"]').forEach(btn => {
    const a = favorites.has(idx);
    btn.classList.toggle('is-active', a);
    btn.querySelector('svg').setAttribute('fill', a ? 'currentColor' : 'none');
  });
  $$('.fav-btn[data-idx="' + idx + '"]').forEach(btn => {
    const a = favorites.has(idx);
    btn.classList.toggle('is-active', a);
    btn.querySelector('svg').setAttribute('fill', a ? 'currentColor' : 'none');
    btn.childNodes[btn.childNodes.length - 1].textContent = a ? ' Favorited' : ' Favorite';
  });
  if (currentFilter === 'favorites') applyFilters();
}

// ── Utilities ────────────────────────────────────────
function hashPalette(str) {
  let h = 0;
  for (let i = 0; i < str.length; i++) h = ((h << 5) - h + str.charCodeAt(i)) | 0;
  return PALETTES[Math.abs(h) % PALETTES.length];
}
function escHtml(s) { const d = document.createElement('div'); d.textContent = s; return d.innerHTML; }

// ── Event Listeners ──────────────────────────────────

// Grid: click card → detail, click heart → favorite, click play → player
grid.addEventListener('click', e => {
  if (e.target.closest('.play-overlay')) { e.stopPropagation(); openPlayer(parseInt(e.target.closest('.play-overlay').dataset.play)); return; }
  if (e.target.closest('.fav-toggle')) { e.stopPropagation(); toggleFavorite(parseInt(e.target.closest('.fav-toggle').dataset.idx)); return; }
  var card = e.target.closest('.card');
  if (card) openDetail(parseInt(card.dataset.idx));
});
grid.addEventListener('keydown', e => { if (e.key === 'Enter') { var c = e.target.closest('.card'); if (c) openDetail(parseInt(c.dataset.idx)); } });

// Image error → fallback
grid.addEventListener('error', e => {
  if (e.target.tagName === 'IMG' && e.target.classList.contains('poster-img')) {
    var wrap = e.target.closest('.poster-wrap'), card = e.target.closest('.card');
    if (wrap && card) {
      e.target.remove();
      var div = document.createElement('div');
      div.className = 'poster-fallback'; div.style.background = card.dataset.bg;
      div.innerHTML = '<span style="color:' + card.dataset.fg + '">' + escHtml(card.dataset.initials) + '</span>';
      wrap.appendChild(div);
    }
  }
}, true);

// Search
var searchTimer;
search.addEventListener('input', () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => { searchQuery = search.value.trim(); applyFilters(); }, 150); });

// Filter chips
$$('.chip').forEach(chip => chip.addEventListener('click', () => { $$('.chip').forEach(c => c.classList.remove('is-active')); chip.classList.add('is-active'); currentFilter = chip.dataset.filter; applyFilters(); }));

// Dropdowns
genreFilter.addEventListener('change', e => { currentGenre = e.target.value; applyFilters(); });
yearFilter.addEventListener('change', e => { currentYear = e.target.value; applyFilters(); });
sortFilter.addEventListener('change', e => { currentSort = e.target.value; applyFilters(); });

// Panel close + favorites + watch
overlay.addEventListener('click', closeDetail);
panel.addEventListener('click', e => {
  if (e.target.closest('.watch-btn')) {
    var idx = parseInt(e.target.closest('.watch-btn').dataset.play);
    if (idx >= 0) { closeDetail(); openPlayer(idx); }
    return;
  }
  if (e.target.closest('.copy-btn')) {
    var url = e.target.closest('.copy-btn').dataset.url;
    if (url) navigator.clipboard.writeText(url).then(function() {
      e.target.closest('.copy-btn').textContent = 'Copied!';
      setTimeout(function() { e.target.closest('.copy-btn').textContent = 'Copy'; }, 1200);
    });
    return;
  }
  if (e.target.closest('.panel-close')) closeDetail();
  if (e.target.closest('.fav-btn')) toggleFavorite(parseInt(e.target.closest('.fav-btn').dataset.idx));
  if (e.target.closest('.panel-edit')) {
    var ef = document.getElementById('editForm');
    if (ef) ef.style.display = ef.style.display === 'none' || !ef.style.display ? 'block' : 'none';
  }
  if (e.target.closest('.edit-save')) {
    var idx = parseInt(e.target.closest('.edit-save').closest('[data-edit]')?.dataset.edit || e.target.closest('.fav-btn')?.dataset.idx);
    // Get the globalIdx from the panel
    var edBtn = panel.querySelector('.panel-edit');
    if (edBtn) idx = parseInt(edBtn.dataset.edit);
    edits[idx] = {
      title: document.getElementById('edTitle')?.value || '',
      year: document.getElementById('edYear')?.value || '',
      rating: document.getElementById('edRating')?.value || '',
      genre: document.getElementById('edGenre')?.value || ''
    };
    saveEdits();
    // Apply edits to the film
    var film = allFilms[idx];
    if (film) {
      var e = edits[idx];
      if (e.title) film.title = e.title;
      if (e.year) film.year = e.year;
      if (e.rating) film.rating = e.rating;
      if (e.genre) film.genre = e.genre;
    }
    // Show saved message
    var msg = document.getElementById('edMsg');
    if (msg) { msg.style.display = 'block'; setTimeout(() => msg.style.display = 'none', 2000); }
    // Update the panel title
    var titleEl = panel.querySelector('.panel-title');
    if (titleEl && film) titleEl.textContent = film.title + (film.year ? ' (' + film.year + ')' : '');
    // Re-render the grid card
    var card = grid.querySelector('.card[data-idx="' + idx + '"]');
    if (card) {
      var titleDiv = card.querySelector('.card-title');
      if (titleDiv) titleDiv.textContent = film.title;
    }
  }
  if (e.target.closest('.edit-cancel')) {
    var ef = document.getElementById('editForm');
    if (ef) ef.style.display = 'none';
  }
});

// Watch buttons (delegated)
document.addEventListener('click', e => {
  var wb = e.target.closest('[data-play]');
  if (wb && !wb.classList.contains('play-overlay')) {
    e.preventDefault(); e.stopPropagation();
    openPlayer(parseInt(wb.dataset.play), wb.dataset.url || null);
  }
});

// Copy to clipboard (delegated)
document.addEventListener('click', e => {
  var cb = e.target.closest('.copy-btn');
  if (!cb || !cb.dataset.url) return;
  if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(cb.dataset.url).then(() => showCopied(cb));
  else { var ta = document.createElement('textarea'); ta.value = cb.dataset.url; ta.style.cssText = 'position:fixed;left:-9999px'; document.body.appendChild(ta); ta.select(); document.execCommand('copy'); document.body.removeChild(ta); showCopied(cb); }
});

function showCopied(btn) {
  btn.classList.add('copied');
  var orig = btn.innerHTML;
  btn.innerHTML = '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"><path d="M20 6L9 17l-5-5"/></svg> Copied';
  setTimeout(() => { btn.classList.remove('copied'); btn.innerHTML = orig; }, 2000);
}

// ── Player Events ────────────────────────────────────
playerBack.addEventListener('click', closePlayer);
playerPlay.addEventListener('click', togglePlayPause);
playerVideo.addEventListener('click', togglePlayPause);
playerVideo.addEventListener('play', () => { iconPlay.classList.add('hidden'); iconPause.classList.remove('hidden'); });
playerVideo.addEventListener('pause', () => { iconPlay.classList.remove('hidden'); iconPause.classList.add('hidden'); });
playerVideo.addEventListener('waiting', () => playerLoading.setAttribute('aria-hidden', 'false'));
playerVideo.addEventListener('canplay', () => playerLoading.setAttribute('aria-hidden', 'true'));
playerVideo.addEventListener('error', () => { playerLoading.setAttribute('aria-hidden', 'true'); playerTime.textContent = 'Playback error'; });
playerVideo.addEventListener('timeupdate', () => {
  var cur = playerVideo.currentTime || 0, dur = playerVideo.duration || 0;
  playerTime.textContent = formatTime(cur) + ' / ' + formatTime(dur);
  if (dur > 0) playerSeek.value = Math.floor((cur / dur) * 1000);
});
playerSeek.addEventListener('input', () => { playerVideo.currentTime = (parseInt(playerSeek.value) / 1000) * (playerVideo.duration || 0); });
playerVol.addEventListener('input', () => playerVideo.volume = parseInt(playerVol.value) / 100);
playerQuality.addEventListener('change', () => {
  if (!currentFilm) return;
  var vl = currentFilm.links.filter(l => /\.(mp4|mkv|webm|mov|avi)$/i.test(lnkUrl(l)));
  var idx = parseInt(playerQuality.value);
  if (vl[idx]) {
    var wasPlaying = !playerVideo.paused, ct = playerVideo.currentTime;
    loadVideoSource(lnkUrl(vl[idx]));
    playerVideo.addEventListener('loadedmetadata', function r() {
      playerVideo.currentTime = ct;
      if (wasPlaying) playerVideo.play().catch(function(){});
      playerVideo.removeEventListener('loadedmetadata', r);
    });
  }
});

// Subtitle change

playerFullscreen.addEventListener('click', () => {
  if (document.fullscreenElement) document.exitFullscreen().catch(function(){});
  else if (playerModal.requestFullscreen) playerModal.requestFullscreen().catch(function(){});
  else if (playerModal.webkitRequestFullscreen) playerModal.webkitRequestFullscreen();
});

// ── Keyboard shortcuts ───────────────────────────────
document.addEventListener('keydown', e => {
  if (playerModal.classList.contains('is-open')) {
    if (e.key === 'Escape') { e.preventDefault(); closePlayer(); return; }
    if (e.key === ' ' && document.activeElement !== playerQuality) { e.preventDefault(); togglePlayPause(); return; }
    if (e.key === 'ArrowLeft') { e.preventDefault(); playerVideo.currentTime = Math.max(0, playerVideo.currentTime - 10); return; }
    if (e.key === 'ArrowRight') { e.preventDefault(); playerVideo.currentTime = Math.min(playerVideo.duration || 0, playerVideo.currentTime + 10); return; }
    if (e.key === 'ArrowUp') { e.preventDefault(); var v = Math.min(100, parseInt(playerVol.value) + 10); playerVol.value = v; playerVideo.volume = v / 100; return; }
    if (e.key === 'ArrowDown') { e.preventDefault(); var v = Math.max(0, parseInt(playerVol.value) - 10); playerVol.value = v; playerVideo.volume = v / 100; return; }
    if (e.key === 'f' || e.key === 'F') { e.preventDefault(); playerFullscreen.click(); return; }
    return;
  }
  if (panel.classList.contains('is-open')) { if (e.key === 'Escape') { e.preventDefault(); closeDetail(); return; } return; }
  if (e.key === '/' && document.activeElement !== search && !e.ctrlKey && !e.metaKey) { e.preventDefault(); search.focus(); }
  if (e.key === 'Escape' && document.activeElement === search) { search.blur(); if (search.value) { search.value = ''; searchQuery = ''; applyFilters(); } }
});

// ── Start ────────────────────────────────────────────
init();

// Kummo — drives every page. Data is loaded from the FastAPI backend (/api/*).
// Field names mirror the Supabase columns (title, price, name, address,
// activity_type, age_group, participants_max, duration, picture, vendor_id, ...).
// Every user-facing string is a key resolved by js/i18n.js against
// static/i18n/<lang>.json — no literal UI text belongs in here. Note: there is no
// `disponibilites`/availability column in the schema, so that data is guarded as
// optional.
let vendors = [];
let activities = [];

// localStorage keys (preferences, bookings, favorites)
const STORAGE_PREFS = 'kummo_prefs';
const STORAGE_BOOKINGS = 'kummo_bookings';
const STORAGE_FAVORITES = 'kummo_favorites';

// The catalogue is loaded before anything renders, so every `t()` below already
// answers in the visitor's language.
async function initApp() {
  await globalThis.KummoI18n?.ready;
  loadData();
}

// =============================================
// 1. Load data from the API
// =============================================
async function loadData() {
  try {
    const [vendorsRes, activitiesRes] = await Promise.all([
      fetch('/api/vendors'),
      fetch('/api/activities'),
    ]);
    if (!vendorsRes.ok) throw new Error(`vendors: ${vendorsRes.status}`);
    if (!activitiesRes.ok) throw new Error(`activities: ${activitiesRes.status}`);
    vendors = await vendorsRes.json();
    activities = await activitiesRes.json();
    initPage();
  } catch (error) {
    console.error('Error while loading data:', error);
    showLoadError();
  }
}

function showLoadError() {
  const msg = `<p class="empty-state" style="color:#DC562E">${t('activity.load_error')}</p>`;
  const el =
    document.getElementById('featured-activities') ||
    document.getElementById('search-results') ||
    document.getElementById('activity-detail');
  if (el) el.innerHTML = msg;
}

// =============================================
// 2. Initialize the page based on the URL
// =============================================
function initPage() {
  const path = window.location.pathname;

  if (path.includes('activity.html')) {
    showActivityDetail();
    return;
  }
  if (path.includes('client.html')) {
    initClientPage();
    return;
  }
  if (path.includes('vendor.html')) {
    // Do nothing here: vendor.html runs its own code
    return;
  }
  if (path.includes('admin.html')) {
    initAdminDashboard();
    return;
  }
  if (path.includes('search.html')) {
    initSearchPage();
    return;
  }
  if (path.includes('index.html') || path.endsWith('/')) {
    showActivityList('featured-activities', activities.slice(0, 6));
    initHomeSearch();
  }
}

// =============================================
// 3. Enrich an activity with its vendor data
// =============================================
function enrichActivity(activity) {
  const vendor = vendors.find((s) => s.id === activity.vendor_id);
  return {
    ...activity,
    address: vendor ? vendor.address : t('activity.address_unknown'),
    vendorName: vendor ? vendor.name : t('activity.vendor_unknown'),
    picture: activity.picture || (vendor ? vendor.picture : 'https://via.placeholder.com/400x250'),
    vendor,
  };
}

// =============================================
// 4. Build the HTML for an activity card
// =============================================
function safeHttpUrl(value, fallback = '') {
  try {
    const url = new URL(String(value ?? ''), window.location.href);
    return url.protocol === 'http:' || url.protocol === 'https:' ? url.href : fallback;
  } catch {
    return fallback;
  }
}

const ACTIVITY_CARD_TEMPLATE = document.createElement('template');
ACTIVITY_CARD_TEMPLATE.innerHTML = `
  <article class="activity-card">
    <img loading="lazy">
    <div class="activity-card-body">
      <div class="activity-meta">
        <span class="tag" data-field="vendor"></span>
        <span class="tag tag-age" data-field="age"></span>
      </div>
      <h3 data-field="title"></h3>
      <p data-field="address"></p>
      <p data-field="details"></p>
      <a class="btn btn-primary btn-sm stretched-link"></a>
    </div>
  </article>`;

function activityCardHtml(activity) {
  const a = enrichActivity(activity);
  const card = ACTIVITY_CARD_TEMPLATE.content.firstElementChild.cloneNode(true);

  const image = card.querySelector('img');
  image.src = safeHttpUrl(a.picture, 'https://via.placeholder.com/400x250');
  image.alt = String(a.title ?? '');

  card.querySelector('[data-field="vendor"]').textContent = String(a.vendorName ?? '');
  card.querySelector('[data-field="age"]').textContent = String(a.age_group ?? '');
  card.querySelector('[data-field="title"]').textContent = String(a.title ?? '');
  card.querySelector('[data-field="address"]').textContent = `📍 ${a.address ?? ''}`;
  card.querySelector('[data-field="details"]').textContent =
    `💰 ${a.price ?? ''} € · 👥 ${a.participants_max ?? ''} · ⏳ ${a.duration ?? ''}`;

  const link = card.querySelector('a');
  link.href = `activity.html?id=${encodeURIComponent(a.id ?? '')}`;
  link.textContent = t('activity.card_cta');

  return card;
}

// =============================================
// 5. Render a grid of activities
// =============================================
function renderActivityGrid(containerId, list) {
  const container = document.getElementById(containerId);
  if (!container) return;

  if (!list.length) {
    const empty = document.createElement('p');
    empty.className = 'empty-state';
    empty.textContent = t('activity.none_found');
    container.replaceChildren(empty);
    return;
  }
  container.replaceChildren(...list.map(activityCardHtml));
}

function showActivityList(containerId, list) {
  renderActivityGrid(containerId, list);
}

// =============================================
// 6. Filter activities
// =============================================
function filterActivities(filters) {
  return activities.filter((activity) => {
    const enriched = enrichActivity(activity);
    const q = (filters.q || '').toLowerCase().trim();

    if (q) {
      const haystack = `${activity.title} ${activity.description} ${enriched.vendorName}`.toLowerCase();
      if (!haystack.includes(q)) return false;
    }

    if (filters.age && filters.age !== 'all') {
      const age = activity.age_group.toLowerCase();
      if (filters.age === '0-5' && !age.includes('3') && !age.includes('5') && !age.includes('0')) return false;
      if (filters.age === '6-12' && !age.includes('6') && !age.includes('12')) return false;
      if (filters.age === '13-18' && !age.includes('18') && !age.includes('13')) return false;
      if (filters.age === 'senioren' && !age.includes('senior')) return false;
    }

    if (filters.maxPrice && activity.price > Number(filters.maxPrice)) return false;

    if (filters.category && filters.category !== 'all') {
      const offering = (enriched.vendor?.activity_type || []).join(' ').toLowerCase();
      const text = `${activity.title} ${activity.description}`.toLowerCase();
      const cat = filters.category;
      if (cat === 'kunst' && !/mal|töpf|illustr|van gogh|impression|druck|kunst|diy/.test(text) && !offering.includes('kunst')) return false;
      if (cat === 'natur' && !/natur|tier|park|steine|dino/.test(text) && !offering.includes('natur')) return false;
      if (cat === 'wissenschaft' && !/wissenschaft|experiment|museum|forscher|steine|dino/.test(text) && !offering.includes('wissenschaft')) return false;
      if (cat === 'geburtstagsfeier' && !offering.includes('geburtstag')) return false;
      if (cat === 'feriencamp' && !offering.includes('camp') && !offering.includes('ferien')) return false;
      if (cat === 'sport' && !/sport|fußball|yoga|bewegung/.test(text)) return false;
    }

    return true;
  });
}

// =============================================
// 7. Search and filter handling
// =============================================
function readFiltersFromForm(form) {
  const fd = new FormData(form);
  return {
    q: fd.get('q') || '',
    age: fd.get('age') || 'all',
    category: fd.get('category') || 'all',
    maxPrice: fd.get('maxPrice') || '',
  };
}

function buildSearchUrl(filters) {
  const params = new URLSearchParams();
  Object.entries(filters).forEach(([k, v]) => {
    if (v && v !== 'all') params.set(k, v);
  });
  const qs = params.toString();
  return `search.html${qs ? `?${qs}` : ''}`;
}

function initHomeSearch() {
  const form = document.getElementById('home-search');
  if (!form) return;
  form.addEventListener('submit', (e) => {
    e.preventDefault();
    window.location.href = buildSearchUrl(readFiltersFromForm(form));
  });
}

function initSearchPage() {
  const params = new URLSearchParams(window.location.search);
  const filters = {
    q: params.get('q') || '',
    category: params.get('category') || 'all',
    age: params.get('age') || 'all',
    maxPrice: params.get('maxPrice') || '',
  };

  const form = document.getElementById('filter-form');
  if (form) {
    if (filters.q) form.querySelector('[name="q"]').value = filters.q;
    if (filters.category) form.querySelector('[name="category"]').value = filters.category;
    if (filters.age) form.querySelector('[name="age"]').value = filters.age;
    if (filters.maxPrice) form.querySelector('[name="maxPrice"]').value = filters.maxPrice;

    form.addEventListener('submit', (e) => {
      e.preventDefault();
      const f = readFiltersFromForm(form);
      renderActivityGrid('search-results', filterActivities(f));
      updateMapHint(filterActivities(f).length);
    });
  }

  const results = filterActivities(filters);
  renderActivityGrid('search-results', results);
  updateMapHint(results.length);
}

function updateMapHint(count) {
  const map = document.getElementById('map-hint');
  if (map) map.textContent = t('search.map_hint', { count });
}

// =============================================
// 8. Activity detail view
// =============================================
function showActivityDetail() {
  const params = new URLSearchParams(window.location.search);
  const activityId = params.get('id');
  const container = document.getElementById('activity-detail');

  if (!activityId || !container) {
    if (container) container.innerHTML = `<p class="empty-state">${t('activity.not_found')}</p>`;
    return;
  }

  const activity = activities.find((a) => a.id === activityId);
  if (!activity) {
    container.innerHTML = `<p class="empty-state">${t('activity.not_found_html')}</p>`;
    return;
  }

  const a = enrichActivity(activity);
  document.title = t('activity.detail_title', { title: a.title });

  container.innerHTML = `
    <div class="detail-hero">
      <img class="gallery-main" src="${a.picture}" alt="${a.title}">
      <div class="detail-info">
        <div class="activity-meta">
          <span class="tag">${a.vendorName}</span>
          <span class="tag tag-age">${a.age_group}</span>
        </div>
        <h1>${a.title}</h1>
        <p class="rating">⭐ ${a.rating || t('activity.not_rated')}</p>
        <p class="price-large">${a.price} € <span style="font-size:1rem;font-weight:600">${t('activity.per_person')}</span></p>
        <p>📍 ${a.address}</p>
        <p>${t('activity.capacity', { count: a.participants_max, duration: a.duration })}</p>
        <p>${a.description}</p>
        <div style="margin-top:1.5rem">
          <h3>${t('activity.slots_title')}</h3>
          <div class="disponibilites">
            ${(a.disponibilites || []).map((d) => `<span class="tag">${d}</span>`).join('')}
          </div>
        </div>
        <div style="display:flex;flex-wrap:wrap;gap:0.75rem;margin-top:1.5rem">
          <button type="button" class="btn btn-primary" id="open-booking">${t('activity.book_now')}</button>
          <button type="button" class="btn btn-outline" id="toggle-fav">${favoriteLabel(a.id)}</button>
        </div>
      </div>
    </div>
    <div class="map-panel">
      <div class="map-placeholder">${t('activity.map_label', { address: a.address })}</div>
    </div>
    <section class="section">
      <h2>${t('activity.similar_title')}</h2>
      <div class="activity-grid" id="similar-activities"></div>
    </section>`;

  const similar = activities
    .filter((x) => x.id !== activity.id && x.vendor_id === activity.vendor_id)
    .slice(0, 3);
  renderActivityGrid('similar-activities', similar.length ? similar : activities.filter((x) => x.id !== activity.id).slice(0, 3));

  document.getElementById('open-booking')?.addEventListener('click', () => openBookingModal(a));
  document.getElementById('toggle-fav')?.addEventListener('click', (e) => {
    toggleFavorite(a.id);
    e.target.textContent = favoriteLabel(a.id);
  });
}

function favoriteLabel(id) {
  return getFavorites().includes(id) ? t('activity.favorite_on') : t('activity.favorite_off');
}

// =============================================
// 9. Booking modal
// =============================================
function openBookingModal(activity) {
  let overlay = document.getElementById('booking-modal');
  if (!overlay) {
    overlay = document.createElement('div');
    overlay.id = 'booking-modal';
    overlay.className = 'modal-overlay';
    document.body.appendChild(overlay);
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) overlay.classList.remove('open');
    });
  }

  const slots = (activity.disponibilites || [])
    .map((s) => `<option value="${s}">${s}</option>`)
    .join('');

  overlay.innerHTML = `
    <div class="modal" role="dialog" aria-labelledby="booking-title">
      <h2 id="booking-title">${t('booking.modal_title', { title: activity.title })}</h2>
      <form id="booking-form">
        <div class="form-row"><label for="b-name">${t('booking.name')}</label><input id="b-name" name="name" required autocomplete="name"></div>
        <div class="form-row"><label for="b-email">${t('booking.email')}</label><input id="b-email" name="email" type="email" required autocomplete="email"></div>
        <div class="form-row"><label for="b-slot">${t('booking.slot')}</label><select id="b-slot" name="slot" required>${slots}</select></div>
        <div class="form-row"><label for="b-qty">${t('booking.people')}</label><input id="b-qty" name="qty" type="number" min="1" max="${activity.participants_max}" value="2" required></div>
        <button type="submit" class="btn btn-primary" style="width:100%;margin-top:0.5rem">${t('booking.submit', { price: activity.price })}</button>
        <button type="button" class="btn btn-outline" style="width:100%;margin-top:0.5rem" data-close>${t('booking.cancel')}</button>
      </form>
    </div>`;

  overlay.classList.add('open');
  overlay.querySelector('[data-close]').addEventListener('click', () => overlay.classList.remove('open'));
  overlay.querySelector('#booking-form').addEventListener('submit', (e) => {
    e.preventDefault();
    const fd = new FormData(e.target);
    const qty = Number(fd.get('qty'));
    addBooking({
      activityId: activity.id,
      activityName: activity.title,
      name: fd.get('name'),
      email: fd.get('email'),
      slot: fd.get('slot'),
      qty,
      total: activity.price * qty,
      // The status is stored as a code, not as text: the booking outlives the
      // language it was made in.
      status: 'confirmed',
      date: new Date().toISOString(),
    });
    overlay.classList.remove('open');
    alert(t('booking.confirmation', { name: fd.get('name') }));
  });
}

// =============================================
// 10. Preferences, bookings and favorites
// =============================================
function getPrefs() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_PREFS) || '{}');
  } catch {
    return {};
  }
}

function savePrefs(prefs) {
  localStorage.setItem(STORAGE_PREFS, JSON.stringify(prefs));
}

function getBookings() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_BOOKINGS) || '[]');
  } catch {
    return [];
  }
}

function addBooking(booking) {
  const list = getBookings();
  list.unshift(booking);
  localStorage.setItem(STORAGE_BOOKINGS, JSON.stringify(list));
}

function getFavorites() {
  try {
    return JSON.parse(localStorage.getItem(STORAGE_FAVORITES) || '[]');
  } catch {
    return [];
  }
}

function toggleFavorite(id) {
  let favs = getFavorites();
  favs = favs.includes(id) ? favs.filter((x) => x !== id) : [...favs, id];
  localStorage.setItem(STORAGE_FAVORITES, JSON.stringify(favs));
  return favs;
}

// =============================================
// 11. Page-specific initializers
// =============================================
// Name and email come from the account, not from the preferences blob: the account
// is authoritative and the user cannot edit them here. The rest stays local.
function applyAccountToClientForm(form, user) {
  form.name.value = user.display_name;
  form.email.value = user.email;
  form.name.readOnly = true;
  form.email.readOnly = true;
}

// This page is for clients only — a vendor is sent to its dashboard by the guard,
// which also drops any locally cached data belonging to a previous account. Nothing
// is rendered before it resolves, so no stale profile is ever shown.
async function initClientPage() {
  const user = await globalThis.KummoAuth?.requireUser('client');
  if (!user) return;

  const form = document.getElementById('prefs-form');
  const prefs = getPrefs();
  if (form) {
    applyAccountToClientForm(form, user);
    if (prefs.age) form.age.value = prefs.age;
    if (prefs.maxBudget) form.maxBudget.value = prefs.maxBudget;
    if (prefs.location) form.location.value = prefs.location;
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      const fd = new FormData(form);
      savePrefs(Object.fromEntries(fd.entries()));
      alert(t('client.saved'));
      renderActivityGrid('recommendations', getRecommendations(getPrefs()));
    });
  }

  renderActivityGrid('recommendations', getRecommendations(getPrefs()));

  const bookingsEl = document.getElementById('booking-history');
  const bookings = getBookings();
  if (bookingsEl) {
    bookingsEl.innerHTML = bookings.length
      ? `<div class="table-wrap"><table><thead><tr><th>${t('client.table.activity')}</th><th>${t('client.table.slot')}</th><th>${t('client.table.price')}</th><th>${t('client.table.status')}</th></tr></thead><tbody>
        ${bookings.map((b) => `<tr><td>${b.activityName}</td><td>${b.slot}</td><td>${b.total} €</td><td>${bookingStatusLabel(b.status)}</td></tr>`).join('')}
      </tbody></table></div>`
      : `<p>${t('client.no_bookings')}</p>`;
  }

  const favIds = getFavorites();
  renderActivityGrid('favorites-list', activities.filter((a) => favIds.includes(a.id)));
}

// Bookings made before the status became a code — and any status the catalogue
// does not know — are shown as they were stored rather than as a missing key.
function bookingStatusLabel(status) {
  return t(`booking.status.${status}`, { defaultValue: status });
}

function getRecommendations(prefs) {
  let list = [...activities];
  if (prefs.maxBudget) list = list.filter((a) => a.price <= Number(prefs.maxBudget));
  if (prefs.age) list = filterActivities({ age: prefs.age });
  return list.slice(0, 6);
}

// =============================================
// 12. Admin dashboard
// =============================================
function initAdminDashboard() {
  document.getElementById('admin-business-count')?.replaceChildren(
    document.createTextNode(String(vendors.length))
  );
  document.getElementById('admin-activity-count')?.replaceChildren(
    document.createTextNode(String(activities.length))
  );
  document.getElementById('admin-booking-count')?.replaceChildren(
    document.createTextNode(String(getBookings().length))
  );
  document.getElementById('admin-revenue')?.replaceChildren(
    document.createTextNode(`${getBookings().reduce((s, b) => s + b.total, 0)} €`)
  );

  const bizTable = document.getElementById('admin-businesses');
  if (bizTable) {
    bizTable.innerHTML = vendors
      .map((b) => {
        const count = activities.filter((a) => a.vendor_id === b.id).length;
        return `<tr><td>${b.name}</td><td>${b.email}</td><td>${count}</td><td>—</td></tr>`;
      })
      .join('');
  }

  const resTable = document.getElementById('admin-reservations');
  if (resTable) {
    const bookings = getBookings();
    resTable.innerHTML = bookings.length
      ? bookings
          .map((b) => {
            const act = activities.find((a) => a.id === b.activityId);
            return `<tr><td>—</td><td>${act ? enrichActivity(act).vendorName : '—'}</td><td>${b.activityName}</td><td>${b.name}</td><td>${b.slot}</td><td>${bookingStatusLabel(b.status)}</td><td>${b.total} €</td></tr>`;
          })
          .join('')
      : `<tr><td colspan="7">${t('admin.no_bookings')}</td></tr>`;
  }
}

// =============================================
// 13. Navigation and chatbot
// =============================================
function initNav() {
  const toggle = document.querySelector('.nav-toggle');
  const nav = document.querySelector('.nav-main');
  if (toggle && nav) {
    toggle.addEventListener('click', () => {
      const open = nav.classList.toggle('open');
      toggle.setAttribute('aria-expanded', open);
    });
  }
}

function initChatbot() {
  const fab = document.getElementById('chat-fab');
  const panel = document.getElementById('chat-panel');
  const input = document.getElementById('chat-input');
  const messages = document.getElementById('chat-messages');
  if (!fab || !panel) return;

  fab.addEventListener('click', () => panel.classList.toggle('open'));

  document.getElementById('chat-send')?.addEventListener('click', () => {
    if (!input?.value.trim()) return;
    messages.innerHTML += `<div><strong>${t('common.chat.you')}</strong> ${input.value}</div>`;
    // Matched in both languages: the visitor types in whichever one they read the
    // page in, and these are the words each question tends to contain.
    const question = input.value.toLowerCase();
    let reply = t('common.chat.reply_default');
    if (/buch|book/.test(question)) reply = t('common.chat.reply_booking');
    if (/klein|toddler|kind|child|3|5/.test(question)) reply = t('common.chat.reply_toddlers');
    messages.innerHTML += `<div class="bot"><strong>${t('common.chat.bot')}</strong> ${reply}</div>`;
    input.value = '';
    messages.scrollTop = messages.scrollHeight;
  });
}

// =============================================
// Final initialization.
// The header's session indicator (name, role, sign in / sign out) is owned by
// auth.js, which initializes itself on every page — nothing to do here.
// =============================================
document.addEventListener('DOMContentLoaded', () => {
  initNav();
  initChatbot();
  initApp();
});

// =============================================
// Test/debug API exposure.
// No effect on browser usage: just attaches an object to globalThis.
// =============================================
if (typeof globalThis !== 'undefined') {
  globalThis.KummoApp = {
    enrichActivity,
    activityCardHtml,
    filterActivities,
    buildSearchUrl,
    getRecommendations,
    getPrefs,
    savePrefs,
    getBookings,
    addBooking,
    getFavorites,
    toggleFavorite,
    bookingStatusLabel,
    STORAGE_PREFS,
    STORAGE_BOOKINGS,
    STORAGE_FAVORITES,
    // Test-only: replaces the data loaded from Supabase.
    __setData: (vendorList, activityList) => {
      vendors = vendorList;
      activities = activityList;
    },
  };
}

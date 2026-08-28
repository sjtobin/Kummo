// =============================================
// Kummo — user-facing text in every supported language.
//
// English is the source language: the text written in the HTML is English and is
// also what a visitor sees if a catalogue fails to load. Every translatable node
// carries a key, and the keys resolve against `static/i18n/<lang>.json` — the only
// files a translator ever has to touch. The format is the one i18next uses
// (nested JSON, `{{name}}` interpolation, `_one`/`_other` plural suffixes), so the
// catalogues can be handed to a translation tool, or to i18next itself, unchanged.
// =============================================

(function () {
  const SUPPORTED = ['en', 'de'];
  const FALLBACK = 'en';
  // Kept out of the sweep in auth.js: the language is a browser preference, not
  // data belonging to the signed-in account.
  const STORAGE_LANG = 'kummo_lang';

  const catalogs = {};
  let current = FALLBACK;

  // =============================================
  // 1. Which language
  // =============================================
  function storedLang() {
    try {
      return localStorage.getItem(STORAGE_LANG);
    } catch (err) {
      return null;
    }
  }

  // An explicit choice wins over the browser; anything unsupported falls back to
  // the source language rather than to a half-translated page.
  function detectLang() {
    const stored = storedLang();
    if (SUPPORTED.includes(stored)) return stored;

    const offered = globalThis.navigator?.languages?.length
      ? globalThis.navigator.languages
      : [globalThis.navigator?.language];
    for (const tag of offered) {
      if (!tag) continue;
      const base = String(tag).toLowerCase().split('-')[0];
      if (SUPPORTED.includes(base)) return base;
    }
    return FALLBACK;
  }

  // =============================================
  // 2. Key lookup
  // =============================================
  function lookup(catalog, key) {
    return key
      .split('.')
      .reduce((node, part) => (node && typeof node === 'object' ? node[part] : undefined), catalog);
  }

  // The requested language first, then the source language: a key a translator has
  // not filled in yet shows up in English instead of disappearing.
  function resolve(key, options) {
    const candidates = [];
    if (typeof options.count === 'number') candidates.push(`${key}_${options.count === 1 ? 'one' : 'other'}`);
    candidates.push(key);

    for (const code of [current, FALLBACK]) {
      const catalog = catalogs[code];
      if (!catalog) continue;
      for (const candidate of candidates) {
        const hit = lookup(catalog, candidate);
        if (typeof hit === 'string') return hit;
      }
    }
    return undefined;
  }

  function escapeHtmlText(value){
    const element = document.createElement('span');
    element.textContent = String(value ?? '');
    return element.innerHTML;
  }

  function interpolate(template, options) {
    return template.replace(/\{\{(\w+)\}\}/g, (whole, name) =>
      Object.prototype.hasOwnProperty.call(options, name) ? String(options[name]) : whole
    );
  }

  function t(key, options = {}) {
    const template = resolve(key, options);
    if (template === undefined) {
      if (typeof options.defaultValue === 'string') return interpolate(options.defaultValue, options);
      console.log(`Missing translation: ${key} (${current})`);
      return key;
    }
    return interpolate(template, options);
  }

  function tHtml(key, options = {}) {
    const safeOptions = {};
    for (const [name, value] of Object.entries(options)) {
      safeOptions[name] = name === 'defaultValue' ? value : escapeHtmlText(value);
    }
    return t(key, safeOptions);
  }

  // =============================================
  // 3. Applying the catalogue to the DOM
  //
  //   data-i18n="key"                    -> textContent
  //   data-i18n-html="key"               -> innerHTML (only for text with markup)
  //   data-i18n-attr="placeholder:key;title:key"
  // =============================================
  const SELECTOR = '[data-i18n],[data-i18n-html],[data-i18n-attr]';

  function translateNode(el) {
    const textKey = el.getAttribute('data-i18n');
    if (textKey) el.textContent = t(textKey);

    const htmlKey = el.getAttribute('data-i18n-html');
    if (htmlKey) el.innerHTML = t(htmlKey);

    const attrSpec = el.getAttribute('data-i18n-attr');
    if (!attrSpec) return;
    for (const pair of attrSpec.split(';')) {
      const [attr, key] = pair.split(':').map((part) => part.trim());
      if (attr && key) el.setAttribute(attr, t(key));
    }
  }

  function apply(root) {
    const scope = root || document;
    scope.querySelectorAll(SELECTOR).forEach(translateNode);
    if (scope === document) document.documentElement.lang = current;
  }

  // =============================================
  // 4. Loading
  // =============================================
  async function load(code) {
    if (catalogs[code]) return catalogs[code];
    try {
      const res = await fetch(`/i18n/${code}.json`);
      if (!res.ok) throw new Error(`i18n/${code}.json: ${res.status}`);
      catalogs[code] = await res.json();
    } catch (err) {
      // The English text in the HTML is the safety net, so a missing catalogue
      // degrades to an untranslated page rather than an empty one.
      console.log(`Could not load the ${code} translations:`, err);
    }
    return catalogs[code];
  }

  // =============================================
  // 5. The language switcher
  //
  // Switching reloads the page: the grids, the detail view and the dashboards are
  // rendered from data, and a reload re-runs exactly the code that produced them —
  // far less to get wrong than a second, translation-only render path.
  // =============================================
  function setLang(code) {
    if (!SUPPORTED.includes(code) || code === current) return;
    try {
      localStorage.setItem(STORAGE_LANG, code);
    } catch (err) {
      console.log('Could not remember the language choice:', err);
    }
    window.location.reload();
  }

  function initSwitcher() {
    document.querySelectorAll('[data-lang]').forEach((button) => {
      const code = button.getAttribute('data-lang');
      button.setAttribute('aria-pressed', String(code === current));
      button.addEventListener('click', () => setLang(code));
    });
  }

  function whenDomReady(fn) {
    if (document.readyState === 'loading') {
      document.addEventListener('DOMContentLoaded', fn);
    } else {
      fn();
    }
  }

  // Everything that renders text waits on this: `apply()` has run and `t()` answers
  // in the visitor's language by the time it resolves.
  const ready = (async () => {
    current = detectLang();
    await Promise.all(Array.from(new Set([current, FALLBACK]), load));
    await new Promise((done) => whenDomReady(done));
    apply();
    initSwitcher();
    return current;
  })();

  // Every page script is a classic script sharing one global scope, so the
  // shorthand is defined once here instead of in each file — two `const t` of
  // their own would be a redeclaration error.
  globalThis.t = t;
  globalThis.tHtml = tHtml;

  globalThis.KummoI18n = {
    t,
    tHtml,
    apply,
    setLang,
    ready,
    SUPPORTED,
    FALLBACK,
    STORAGE_LANG,
    lang: () => current,
    // Test-only: inject a catalogue instead of fetching it.
    __setCatalog: (code, catalog) => {
      catalogs[code] = catalog;
      current = code;
    },
  };
})();

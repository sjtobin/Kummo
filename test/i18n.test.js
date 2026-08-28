// @vitest-environment jsdom
//
// Tests for js/i18n.js — the runtime the whole UI's text goes through.
// test/setup.js has already imported it and injected the English catalogue.
import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { readFileSync, readdirSync } from 'node:fs';
import { resolve } from 'node:path';

const i18n = globalThis.KummoI18n;

// vitest runs from the repository root.
const read = (code) =>
  JSON.parse(readFileSync(resolve(process.cwd(), `static/i18n/${code}.json`), 'utf8'));

const en = read('en');
const de = read('de');

// Every key of a catalogue, flattened to its dotted path.
function keyPaths(node, prefix = '') {
  return Object.entries(node).flatMap(([key, value]) =>
    value && typeof value === 'object' ? keyPaths(value, `${prefix}${key}.`) : [`${prefix}${key}`]
  );
}

beforeEach(() => {
  i18n.__setCatalog('en', en);
});

afterEach(() => {
  i18n.__setCatalog('en', en);
});

describe('the catalogues', () => {
  it('carry exactly the same keys in every language', () => {
    // The guard for translators: a key added to English but not to German (or a
    // stale German key) is caught here rather than as a placeholder on the page.
    expect(keyPaths(de).sort()).toEqual(keyPaths(en).sort());
  });

  it('leaves no placeholder unfilled in a translation', () => {
    const placeholders = (text) => (text.match(/\{\{(\w+)\}\}/g) ?? []).sort();
    const flat = (node, prefix = '') =>
      Object.entries(node).flatMap(([key, value]) =>
        value && typeof value === 'object'
          ? flat(value, `${prefix}${key}.`)
          : [[`${prefix}${key}`, value]]
      );
    const german = Object.fromEntries(flat(de));

    for (const [key, text] of flat(en)) {
      expect([key, placeholders(german[key])]).toEqual([key, placeholders(text)]);
    }
  });
});

describe('the pages', () => {
  const pages = readdirSync(resolve(process.cwd(), 'static')).filter((f) => f.endsWith('.html'));

  // Every key written into a page must exist, or the visitor gets a dotted path
  // where a sentence belongs. Catching that here beats catching it in the browser.
  it.each(pages)('%s only uses keys the catalogue defines', (page) => {
    const html = readFileSync(resolve(process.cwd(), 'static', page), 'utf8');
    const keys = [
      ...[...html.matchAll(/data-i18n(?:-html)?="([^"]+)"/g)].map((m) => m[1]),
      ...[...html.matchAll(/data-i18n-attr="([^"]+)"/g)].flatMap((m) =>
        m[1].split(';').map((pair) => pair.split(':')[1].trim())
      ),
    ];

    expect(keys.length).toBeGreaterThan(0);
    expect(keys.filter((key) => !keyPaths(en).includes(key))).toEqual([]);
  });
});

describe('t', () => {
  it('resolves a nested key', () => {
    expect(i18n.t('common.nav.activities')).toBe('Activities');
  });

  it('interpolates named values', () => {
    expect(i18n.t('activity.detail_title', { title: 'Van Gogh' })).toBe('Van Gogh — Kummo');
  });

  it('escapes interpolated values in HTML translations', () => {
    const attack = '<img src=x onerror="alert(1)">';
    const host = document.createElement('div');

    host.innerHTML = i18n.tHtml('vendor.subheading', { name: attack });

    expect(host.querySelector('strong')).not.toBeNull();
    expect(host.querySelector('strong').textContent).toBe(attack);
    expect(host.querySelector('img')).toBeNull();
  });

  it('leaves a placeholder alone when no value is given', () => {
    expect(i18n.t('activity.detail_title')).toContain('{{title}}');
  });

  it('picks the singular and the plural form by count', () => {
    expect(i18n.t('search.map_hint', { count: 1 })).toContain('1 activity in Berlin');
    expect(i18n.t('search.map_hint', { count: 4 })).toContain('4 activities in Berlin');
  });

  it('returns the key itself when it is missing', () => {
    expect(i18n.t('nope.not.here')).toBe('nope.not.here');
  });

  it('prefers an explicit default over the key', () => {
    expect(i18n.t('booking.status.pending', { defaultValue: 'pending' })).toBe('pending');
  });

  it('falls back to English for a key a translation has not filled in', () => {
    i18n.__setCatalog('de', { common: { nav: { login: 'Anmelden' } } });

    expect(i18n.t('common.nav.login')).toBe('Anmelden');
    expect(i18n.t('common.nav.activities')).toBe('Activities');
  });
});

describe('apply', () => {
  beforeEach(() => {
    document.body.innerHTML = `
      <h1 data-i18n="client.heading">placeholder</h1>
      <p data-i18n-html="vendor.subheading">placeholder</p>
      <input data-i18n-attr="placeholder:filters.search_placeholder;aria-label:filters.keyword">
    `;
  });

  it('fills text, markup and attributes from the catalogue', () => {
    i18n.apply();

    expect(document.querySelector('h1').textContent).toBe('My profile');
    expect(document.querySelector('p').innerHTML).toContain('<strong>');
    const input = document.querySelector('input');
    expect(input.getAttribute('placeholder')).toBe('Search…');
    expect(input.getAttribute('aria-label')).toBe('Keyword');
  });

  it('records the language on the document', () => {
    i18n.__setCatalog('de', de);
    i18n.apply();

    expect(document.documentElement.lang).toBe('de');
    expect(document.querySelector('h1').textContent).toBe('Mein Profil');
  });
});

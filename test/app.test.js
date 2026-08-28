// @vitest-environment jsdom
//
// Regression tests for js/app.js.
// app.js is a "classic" script (loaded via <script> in the browser).
// We import it here for its side effect: it attaches its API to globalThis.KummoApp.
import { describe, it, expect, beforeEach } from 'vitest';
import '../static/js/app.js';

const app = globalThis.KummoApp;

const clone = (x) => JSON.parse(JSON.stringify(x));

const vendors = [
  {
    id: 's1',
    name: 'Lila Farbe',
    address: 'Kreuzberg, Berlin',
    picture: 'vendor.jpg',
    activity_type: ['Kunst'],
  },
];

const activities = [
  {
    id: 'a1',
    vendor_id: 's1',
    title: 'Van Gogh Malkurs',
    description: 'Malen wie die Großen',
    price: 25,
    participants_max: 8,
    duration: '2 Stunden',
    age_group: '6-12 Jahre',
    picture: 'a1.jpg',
  },
  {
    // vendor_id points to a missing vendor -> exercises the fallback
    id: 'a2',
    vendor_id: 's2',
    title: 'Fußball Camp',
    description: 'Sport für alle',
    price: 50,
    participants_max: 20,
    duration: '3 Stunden',
    age_group: '6-12 Jahre',
  },
];

beforeEach(() => {
  app.__setData(clone(vendors), clone(activities));
  localStorage.clear();
});

describe('STORAGE constants', () => {
  it('are defined (regression: ReferenceError on the profile page)', () => {
    expect(app.STORAGE_PREFS).toBeTruthy();
    expect(app.STORAGE_BOOKINGS).toBeTruthy();
    expect(app.STORAGE_FAVORITES).toBeTruthy();
  });
});

describe('enrichActivity', () => {
  it('joins the vendor via vendor_id', () => {
    const e = app.enrichActivity(activities[0]);
    expect(e.vendorName).toBe('Lila Farbe');
    expect(e.address).toBe('Kreuzberg, Berlin');
  });

  it('uses a fallback when the vendor is missing', () => {
    const e = app.enrichActivity(activities[1]);
    expect(e.vendorName).toBe('Vendor unknown');
    expect(e.address).toBe('Address unknown');
  });
});

describe('activityCardHtml', () => {
  it('interpolates values and never emits a literal ${ (regression: escaped template literals)', () => {
    const card = app.activityCardHtml(activities[0]);
    expect(card.textContent).toContain('Van Gogh Malkurs');
    expect(card.textContent).toContain('Kreuzberg, Berlin');
    expect(card.textContent).toContain('25 €');
    expect(card.textContent).toContain('Lila Farbe');
    expect(card.textContent).not.toContain('${');
  });

  it('renders activity text as text rather than HTML', () => {
    const attack = '<img src=x onerror="alert(1)">';
    const card = app.activityCardHtml({
      ...activities[0],
      title: attack,
    });

    const title = card.querySelector('[data-field="title"]');

    expect(title.textContent).toBe(attack);
    expect(title.querySelector('img')).toBeNull();
  });
});

describe('buildSearchUrl', () => {
  it('encodes only meaningful filters and emits no literal ${ (regression)', () => {
    const url = app.buildSearchUrl({ q: 'malen', age: 'all', category: 'kunst', maxPrice: '' });
    expect(url.startsWith('search.html?')).toBe(true);
    expect(url).toContain('q=malen');
    expect(url).toContain('category=kunst');
    expect(url).not.toContain('age=all');
    expect(url).not.toContain('${');
  });

  it('returns the bare page when there are no filters', () => {
    expect(app.buildSearchUrl({ age: 'all', category: 'all' })).toBe('search.html');
  });
});

describe('filterActivities', () => {
  it('searches free text across title/description/vendor', () => {
    expect(app.filterActivities({ q: 'van gogh' }).map((a) => a.id)).toEqual(['a1']);
  });

  it('applies a maximum price', () => {
    expect(app.filterActivities({ maxPrice: '30' }).map((a) => a.id)).toEqual(['a1']);
  });

  it('filters by category (vendor offering + text)', () => {
    expect(app.filterActivities({ category: 'kunst' }).map((a) => a.id)).toEqual(['a1']);
  });

  it('returns everything when no filter is set', () => {
    expect(app.filterActivities({}).length).toBe(2);
  });
});

describe('localStorage helpers', () => {
  it('round-trips preferences', () => {
    app.savePrefs({ name: 'Anna', maxBudget: '30' });
    expect(app.getPrefs()).toEqual({ name: 'Anna', maxBudget: '30' });
  });

  it('adds bookings most-recent-first', () => {
    app.addBooking({ activityId: 'a1', total: 50 });
    app.addBooking({ activityId: 'a2', total: 100 });
    const list = app.getBookings();
    expect(list).toHaveLength(2);
    expect(list[0].activityId).toBe('a2');
  });

  it('toggles a favorite on then off', () => {
    app.toggleFavorite('a1');
    expect(app.getFavorites()).toContain('a1');
    app.toggleFavorite('a1');
    expect(app.getFavorites()).not.toContain('a1');
  });
});

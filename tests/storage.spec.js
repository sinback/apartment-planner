// Saving and loading layouts: IndexedDB, migration from the localStorage-era app, and fallback.
// Each test gets a fresh browser context, so storage starts empty.
const { test, expect } = require('@playwright/test');
const { LEGACY_KEY, DEFAULT_PIECE_COUNT, openApp, readDb, dragBy, collectPageErrors } = require('./helpers');

test('first visit shows the default layout and creates both stores', async ({ page }) => {
  const errors = collectPageErrors(page);
  await openApp(page);

  await expect.poll(async () => (await readDb(page)).layout?.pieces.length).toBe(DEFAULT_PIECE_COUNT);
  const db = await readDb(page);
  expect(db.stores).toEqual(['floorplans', 'layouts']);
  expect(db.floorplans.map(p => p.id)).toEqual(['default']);
  // runtime ids are not stored
  expect(db.layout.pieces.every(p => !('id' in p))).toBe(true);
  // the old localStorage key is not written any more
  expect(await page.evaluate(k => localStorage.getItem(k), LEGACY_KEY)).toBeNull();
  expect(errors).toEqual([]);
});

test('a dragged piece keeps its new position after a reload', async ({ page }) => {
  await openApp(page);
  const tvBefore = (await readTv(page));

  await dragBy(page, page.locator('#pieces .piece').first(), 60, 30);
  // saving is asynchronous: wait until the move is stored
  await expect.poll(async () => (await readTv(page))?.x).not.toBe(tvBefore?.x);
  const tvAfter = await readTv(page);
  expect(tvAfter.x).toBeGreaterThan(tvBefore.x);
  expect(tvAfter.y).toBeGreaterThan(tvBefore.y);

  await page.reload();
  await expect(page.locator('#pieces .piece')).toHaveCount(DEFAULT_PIECE_COUNT);
  expect(await readTv(page)).toEqual(tvAfter);
});

test('a layout saved by the localStorage-era app is migrated', async ({ page }) => {
  const legacy = [
    { shape: 'rect', name: 'Old sofa', w: 84, d: 36, x: 100, y: 100, rot: 0, color: '#2f6fd6', id: 7 },
    { shape: 'circle', name: 'Old table', r: 20, x: 200, y: 150, rot: 0, color: '#d9822b', id: 8 },
  ];
  // Put the old key in place before the app's first run in this browser.
  await page.addInitScript(([k, v]) => { if (!sessionStorage.getItem('seeded')) { localStorage.setItem(k, v); sessionStorage.setItem('seeded', '1'); } },
    [LEGACY_KEY, JSON.stringify(legacy)]);

  await openApp(page, { expectPieces: 2 });
  await expect(page.locator('#list')).toContainText('Old sofa');

  const db = await readDb(page);
  expect(db.layout.pieces.map(p => p.name)).toEqual(['Old sofa', 'Old table']);
  // the old key is kept as a backup
  expect(JSON.parse(await page.evaluate(k => localStorage.getItem(k), LEGACY_KEY))).toHaveLength(2);
});

test('falls back to localStorage when IndexedDB is unavailable', async ({ page }) => {
  await page.addInitScript(() => Object.defineProperty(window, 'indexedDB', { value: undefined, configurable: true }));
  const errors = collectPageErrors(page);
  await openApp(page);

  await page.locator('#addRect button[type=submit]').click();
  await expect(page.locator('#pieces .piece')).toHaveCount(DEFAULT_PIECE_COUNT + 1);
  await page.reload();
  await expect(page.locator('#pieces .piece')).toHaveCount(DEFAULT_PIECE_COUNT + 1);
  expect(JSON.parse(await page.evaluate(k => localStorage.getItem(k), LEGACY_KEY))).toHaveLength(DEFAULT_PIECE_COUNT + 1);
  expect(errors).toEqual([]);
});

const readTv = page => page.evaluate(async () => {
  const db = await idb.openDB('apartment-planner');
  const rec = await db.get('layouts', 'default');
  db.close();
  const tv = rec && rec.pieces.find(p => p.name === 'TV + Stand');
  return tv ? { x: tv.x, y: tv.y } : null;
});

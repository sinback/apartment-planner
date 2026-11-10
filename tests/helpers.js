// Shared helpers for the browser tests.
const { expect } = require('@playwright/test');

const LEGACY_KEY = 'apt-furniture-layout-v1';
const DEFAULT_PIECE_COUNT = 29; // pieces in DEFAULT_LAYOUT (app.js)

// Open the app and wait until the saved (or default) layout has been drawn.
async function openApp(page, { expectPieces = DEFAULT_PIECE_COUNT } = {}) {
  await page.goto('/index.html');
  await expect(page.locator('#pieces .piece')).toHaveCount(expectPieces);
}

// Read the app's IndexedDB contents through the idb library the page already loads.
function readDb(page) {
  return page.evaluate(async () => {
    const db = await idb.openDB('apartment-planner');
    const out = {
      stores: [...db.objectStoreNames].sort(),
      floorplans: await db.getAll('floorplans'),
      layout: (await db.get('layouts', 'default')) || null,
    };
    db.close();
    return out;
  });
}

// Drag the element under `locator` by (dx, dy) screen pixels.
async function dragBy(page, locator, dx, dy) {
  const box = await locator.boundingBox();
  const x = box.x + box.width / 2, y = box.y + box.height / 2;
  await page.mouse.move(x, y);
  await page.mouse.down();
  await page.mouse.move(x + dx, y + dy, { steps: 5 });
  await page.mouse.up();
}

// Fail the test on uncaught page errors. Returns the list so a test can inspect it.
function collectPageErrors(page) {
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  return errors;
}

module.exports = { LEGACY_KEY, DEFAULT_PIECE_COUNT, openApp, readDb, dragBy, collectPageErrors };

// Sharing a layout: Export file downloads a JSON file the app can import again.
const { test, expect } = require('@playwright/test');
const fs = require('fs');
const { DEFAULT_PIECE_COUNT, openApp, collectPageErrors } = require('./helpers');

test('Export file is visible and downloads the layout as JSON', async ({ page }) => {
  const errors = collectPageErrors(page);
  await openApp(page);

  const button = page.locator('#exportFile');
  await expect(button).toBeVisible();
  const [download] = await Promise.all([page.waitForEvent('download'), button.click()]);

  expect(download.suggestedFilename()).toMatch(/^furniture-layout-\d{4}-\d{2}-\d{2}-\d{4}\.json$/);
  const data = JSON.parse(fs.readFileSync(await download.path(), 'utf8'));
  expect(data.app).toBe('apartment-furniture-planner');
  expect(data.version).toBe(1);
  expect(data.pieces).toHaveLength(DEFAULT_PIECE_COUNT);
  await expect(page.locator('#ioMsg')).toHaveText(`Downloaded ${DEFAULT_PIECE_COUNT} pieces as a .json file.`);
  expect(errors).toEqual([]);
});

test('an exported file can be imported back', async ({ page }) => {
  await openApp(page);
  const [download] = await Promise.all([page.waitForEvent('download'), page.locator('#exportFile').click()]);
  const file = await download.path();

  // Clear everything, then import the export.
  await page.locator('#clearAll').click();
  await page.getByRole('button', { name: 'Remove all' }).click();
  await expect(page.locator('#pieces .piece')).toHaveCount(0);

  await page.locator('#importFile').setInputFiles({ name: 'layout.json', mimeType: 'application/json', buffer: fs.readFileSync(file) });
  await expect(page.locator('#pieces .piece')).toHaveCount(DEFAULT_PIECE_COUNT);
  await expect(page.locator('#ioMsg')).toContainText(`Loaded ${DEFAULT_PIECE_COUNT} pieces`);
});

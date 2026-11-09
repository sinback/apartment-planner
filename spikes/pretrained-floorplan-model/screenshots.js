// Screenshot the plan in each display mode (same zoom), light and dark.
// Usage: node screenshots.js ../../index.html output/
const { chromium } = require('playwright');
const path = require('path');

(async () => {
  const [index, outDir] = process.argv.slice(2);
  const browser = await chromium.launch();
  for (const scheme of ['light', 'dark']) {
    const page = await browser.newPage({ viewport: { width: 1400, height: 1000 }, deviceScaleFactor: 2, colorScheme: scheme });
    const errors = [];
    page.on('pageerror', e => errors.push(String(e)));
    page.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
    await page.goto('file://' + path.resolve(index));
    await page.waitForTimeout(500);
    const modes = scheme === 'light' ? ['original', 'model', 'overlay'] : ['model', 'overlay'];
    for (const mode of modes) {
      await page.selectOption('#planMode', mode);
      await page.waitForTimeout(150);
      const file = path.join(outDir, `app_${mode}_${scheme}.png`);
      await page.locator('#stage').screenshot({ path: file });
      console.log(file);
    }
    if (errors.length) console.log(scheme, 'page errors:', errors);
    await page.close();
  }
  await browser.close();
})();

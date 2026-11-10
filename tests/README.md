# Browser tests

End-to-end tests that drive the real app in a headless browser with [Playwright](https://playwright.dev/).
They serve the repo as static files, the same way GitHub Pages does.

## Running them

Needs Node.js and Python 3 (Python serves the files).

```bash
npm install
npx playwright install chromium   # first time only: downloads the browser
npm test
```

Useful variations:

```bash
npx playwright test tests/storage.spec.js   # one file
npx playwright test --headed                # watch the browser
npx playwright test --ui                    # interactive runner with time-travel debugging
```

## In CI

`.github/workflows/tests.yml` runs the suite on every pull request and on pushes to `main`.
If a run fails, its HTML report (with a trace of the failing test) is attached to the run as
the `playwright-report` artifact.

## Writing tests

- Each test gets a fresh browser context, so storage (IndexedDB, localStorage) starts empty.
- `helpers.js` has `openApp()` (load and wait for the layout to draw), `readDb()` (read the app's
  IndexedDB), and `dragBy()`.
- The app saves asynchronously, so check stored values with `expect.poll(...)`, not a fixed wait.

/* Run with NODE_PATH pointing at an existing Playwright installation.
 * BASE_URL must serve web_dashboard (the runner never starts a server).
 * DASHBOARD_FIXTURE and SCREENSHOT_DIR are optional absolute paths.
 * Synthetic data is intercepted in the browser only; it is never copied to public data/.
 */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

async function main() {
  const baseURL = process.env.BASE_URL || 'http://127.0.0.1:8000/';
  const fixture = JSON.parse(fs.readFileSync(process.env.DASHBOARD_FIXTURE || path.join(__dirname, 'fixtures/dashboard/synthetic-dashboard.json'), 'utf8'));
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  await context.addInitScript(() => {
    const NativeDate = Date;
    const now = NativeDate.parse('2026-10-02T18:00:00Z');
    window.Date = class extends NativeDate {
      constructor(...args) { super(...(args.length ? args : [now])); }
      static now() { return now; }
    };
  });
  let data = structuredClone(fixture);
  let httpStatus = 200;
  let requests = 0;
  let releaseResponse;
  let holdResponse = false;
  await context.route('**/data/dashboard.json', async route => {
    requests++;
    if (holdResponse) await new Promise(resolve => { releaseResponse = resolve; });
    await route.fulfill({ status: httpStatus, contentType: 'application/json', body: JSON.stringify(data) });
  });
  const page = await context.newPage();
  const pageErrors = [];
  page.on('pageerror', error => pageErrors.push(error.message));
  async function load(nextData = fixture) {
    data = structuredClone(nextData);
    requests = 0;
    await page.goto(baseURL, { waitUntil: 'networkidle' });
    await page.locator('#load-status').waitFor({ state: 'visible' });
  }
  async function ready() {
    await page.locator('#dashboard').waitFor({ state: 'visible' });
    await page.waitForFunction(() => document.querySelector('#load-status').dataset.state === 'ready');
    assert.equal(requests, 1, 'one bundle fetch per page load');
  }
  async function noOverflow() {
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true, 'no page-wide horizontal overflow');
  }
  try {
    holdResponse = true;
    await page.goto(baseURL, { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => document.querySelector('#load-status').textContent.includes('Loading'));
    assert.equal(await page.locator('#dashboard').isVisible(), false);
    holdResponse = false;
    await page.waitForFunction(() => document.readyState === 'complete');
    while (!releaseResponse) await new Promise(resolve => setTimeout(resolve, 10));
    releaseResponse();
    await ready();
    assert.match(await page.locator('#synthetic-notice').textContent(), /Synthetic test data/);
    assert.equal(await page.locator('main section').count(), 6);
    assert.match(await page.locator('#total-movies').textContent(), /12/);
    assert.match(await page.locator('#histogram-population').textContent(), /5/);
    assert.equal(await page.locator('.js-plotly-plot').count(), 5, 'all five charts use the pinned Plotly runtime');
    assert.equal(await page.evaluate(() => window.Plotly.version), '4.1.1');
    await page.locator('#people-role').selectOption('director');
    assert.match(await page.locator('#people-table').textContent(), /Synthetic Director B/);
    assert.doesNotMatch(await page.locator('#people-table').textContent(), /Synthetic Actor A/);
    await page.locator('#people-role').selectOption('writer');
    assert.match(await page.locator('#people-table').textContent(), /No people qualify/);
    await page.locator('#market').selectOption('IN');
    assert.match(await page.locator('#recommendations').textContent(), /No recommendations qualify/);
    assert.match(await page.locator('#market-snapshot').textContent(), /India/);
    assert.equal(requests, 1, 'local controls must not refetch data');
    await page.locator('#market').selectOption('US');
    await page.locator('#people-role').selectOption('actor');
    await noOverflow();
    await page.keyboard.press('Tab');
    assert.ok(await page.evaluate(() => document.activeElement !== document.body), 'keyboard focus reaches a control');
    if (process.env.SCREENSHOT_DIR) {
      fs.mkdirSync(process.env.SCREENSHOT_DIR, { recursive: true });
      await page.screenshot({ path: path.join(process.env.SCREENSHOT_DIR, 'dashboard-desktop.png'), fullPage: true });
    }
    await page.setViewportSize({ width: 390, height: 844 });
    await noOverflow();
    if (process.env.SCREENSHOT_DIR) await page.screenshot({ path: path.join(process.env.SCREENSHOT_DIR, 'dashboard-mobile.png'), fullPage: true });

    for (const staleField of ['build', 'US', 'IN']) {
      const old = structuredClone(fixture);
      if (staleField === 'build') old.metadata.warehouse_completed_at = '2026-09-23T18:00:00Z';
      else old.metadata.tmdb_capture_dates[staleField] = '2026-09-23';
      await load(old);
      await ready();
      assert.match(await page.locator('#freshness-notice').textContent(), /Stale data/);
    }
    const boundary = structuredClone(fixture);
    boundary.metadata.warehouse_completed_at = '2026-09-24T18:00:00Z';
    boundary.metadata.tmdb_capture_dates = { US: '2026-09-24', IN: '2026-09-24' };
    await load(boundary);
    await ready();
    assert.equal(await page.locator('#freshness-notice').isVisible(), false, 'exactly eight days is not stale');

    const sparse = structuredClone(fixture);
    sparse.overview.avg_rating = null;
    sparse.overview.avg_runtime_minutes = null;
    sparse.overview.highest_rated_movie = null;
    sparse.ratings = { population_count: 0, bins: [] };
    sparse.genres = { ratings: [], runtimes: [] };
    sparse.eras = { counts: [], ratings: [], top_years: [] };
    sparse.top_movies = [];
    sparse.people = [];
    await load(sparse);
    await ready();
    assert.match(await page.locator('#average-rating').textContent(), /Unavailable/);
    assert.match(await page.locator('#highest-rated').textContent(), /No qualifying movie/);
    assert.match(await page.locator('#histogram-table').textContent(), /No qualifying movies/);

    const hostile = structuredClone(fixture);
    const attack = '<img src=x onerror="window.__dashboardInjected=1"> & <b>literal</b>';
    hostile.overview.highest_rated_movie.title = attack;
    hostile.top_movies[0].title = attack;
    hostile.people[0].name = attack;
    hostile.genres.ratings[0].genre = attack;
    hostile.genres.runtimes[0].genre = attack;
    hostile.now_playing.regions.US.recommendations[0].title = attack;
    hostile.now_playing.regions.US.recommendations[0].overview = attack;
    hostile.metadata.limitations = [attack];
    await load(hostile);
    await ready();
    assert.ok((await page.locator('#top-movies-table').textContent()).includes(attack), 'source strings remain literal');
    assert.equal(await page.locator('main img, main script, main a[href="x"]').count(), 0, 'source data cannot create elements');
    assert.equal(await page.evaluate(() => window.__dashboardInjected), undefined);
    assert.ok((await page.locator('#genre-ratings-chart .ytick').first().textContent()).includes('<img'), 'Plotly axis text displays the literal angle bracket');
    await noOverflow();

    data = structuredClone(fixture);
    requests = 0;
    releaseResponse = undefined;
    holdResponse = true;
    await page.goto(baseURL, { waitUntil: 'domcontentloaded' });
    await page.waitForFunction(() => typeof window.Plotly?.newPlot === 'function');
    await page.evaluate(() => {
      const newPlot = window.Plotly.newPlot;
      window.Plotly.newPlot = function (node, ...args) {
        if (node.id === 'histogram-chart') {
          node.textContent = 'Partial chart content';
          return Promise.reject(new Error('Simulated chart render rejection'));
        }
        return newPlot.call(this, node, ...args);
      };
    });
    while (!releaseResponse) await new Promise(resolve => setTimeout(resolve, 10));
    holdResponse = false;
    releaseResponse();
    await ready();
    assert.match(await page.locator('#histogram-chart').textContent(), /This chart could not render/);
    assert.doesNotMatch(await page.locator('#histogram-chart').textContent(), /Partial chart content/);
    assert.equal(await page.locator('.js-plotly-plot').count(), 4, 'one rejected chart does not prevent the other charts rendering');
    await page.locator('#histogram-table').locator('..').locator('summary').click();
    assert.equal(await page.locator('#histogram-table table').isVisible(), true, 'failed chart keeps its data table available');
    assert.match(await page.locator('#histogram-table').textContent(), /9-10/);
    assert.match(await page.locator('#histogram-table').textContent(), /40\.0%/);

    await context.route('**/assets/vendor/plotly-basic-4.1.1.min.js', route => route.abort());
    await load();
    await ready();
    assert.match(await page.locator('#histogram-chart').textContent(), /chart library could not load/);
    await page.locator('#histogram-table').locator('..').locator('summary').click();
    assert.match(await page.locator('#histogram-table').textContent(), /Rating distribution/);
    await context.unroute('**/assets/vendor/plotly-basic-4.1.1.min.js');

    await load({ ...fixture, schema_version: 99 });
    assert.match(await page.locator('#load-status').textContent(), /unsupported data version/i);
    assert.equal(await page.locator('#dashboard').isVisible(), false);
    await load({ schema_version: 1 });
    assert.match(await page.locator('#load-status').textContent(), /could not be loaded/i);
    httpStatus = 503;
    await load();
    assert.match(await page.locator('#load-status').textContent(), /could not be loaded/i);
    assert.equal(await page.locator('#dashboard').isVisible(), false);
    assert.deepEqual(pageErrors, [], 'no uncaught browser errors');
    console.log('Dashboard smoke passed: loading, desktop/mobile, controls, freshness, empty/null, literal text, chart rejection fallback, version, invalid bundle and HTTP error.');
  } finally {
    await browser.close();
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });

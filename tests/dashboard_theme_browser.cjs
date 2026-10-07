/* Theme interactions reuse an existing bundle; no exported datasets are created. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

async function main() {
  const url = new URL(process.env.DASHBOARD_ENTRY || 'redesign.html', process.env.BASE_URL || 'http://127.0.0.1:8766/').href;
  const bundle = JSON.parse(fs.readFileSync(process.env.DASHBOARD_FIXTURE || path.join(__dirname, 'fixtures/dashboard/synthetic-dashboard.json'), 'utf8'));
  const browser = await chromium.launch({ headless: true });
  const errors = [];
  async function newContext(blockStorage = false, responseBundle = bundle) {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, colorScheme: 'light' });
    if (blockStorage) await context.addInitScript(() => {
      Object.defineProperty(window, 'localStorage', { get() { throw new DOMException('Storage disabled', 'SecurityError'); } });
    });
    await context.route('**/data/dashboard.json', route => route.fulfill({ json: responseBundle }));
    const page = await context.newPage();
    page.on('pageerror', error => errors.push(error.message));
    return { context, page };
  }
  async function ready(page) {
    await page.waitForFunction(() => document.getElementById('load-status').dataset.state === 'ready');
  }
  async function themeReady(page, theme) {
    await page.waitForFunction(expected => {
      const root = document.documentElement;
      const surface = getComputedStyle(root).getPropertyValue('--panel').trim();
      return root.dataset.theme === expected && [...document.querySelectorAll('.js-plotly-plot')].every(node => !node.data?.length || node.layout.paper_bgcolor === surface);
    }, theme);
    const colors = await page.evaluate(() => {
      const styles = getComputedStyle(document.documentElement);
      return {
        runtime: styles.getPropertyValue('--runtime').trim(),
        line: document.getElementById('decade-ratings-chart').data[0].line.color,
        countHigh: styles.getPropertyValue('--count-high').trim(),
        countNeutral: styles.getPropertyValue('--chart-context').trim(),
        expectedDotColors: ['count-low', 'count-mid', 'count-high'].map(token => styles.getPropertyValue(`--${token}`).trim()),
        expectedLegendColors: ['count-low', 'count-mid', 'count-high'].map(token => {
          const probe = document.createElement('span');
          probe.style.color = styles.getPropertyValue(`--${token}`).trim();
          return probe.style.color;
        }),
        legendColors: ['top-movies', 'top-years', 'people'].map(id =>
          [...document.querySelectorAll(`#${id}-size-key .size-key-circle`)].map(swatch => swatch.style.backgroundColor)),
        charts: ['top-movies', 'top-years', 'people'].map(id => ({
          id,
          colors: document.getElementById(`${id}-chart`).data[0].marker.color,
          sizes: document.getElementById(`${id}-chart`).data[0].marker.size,
          symbols: document.getElementById(`${id}-chart`).data[0].marker.symbol,
        })),
        market: document.getElementById('market').value,
        marketColor: document.getElementById('now-playing-chart').data?.[0]?.marker.color,
        expectedMarketColor: styles.getPropertyValue(document.getElementById('market').value === 'IN' ? '--market-india' : '--green').trim(),
      };
    });
    assert.equal(colors.line, colors.runtime, 'amber line recolors with the theme');
    for (const legend of colors.legendColors) {
      if (legend.length === 3) assert.deepEqual(legend, colors.expectedLegendColors, 'legend references use separate blue, green and red colors without blending');
    }
    for (const chart of colors.charts) {
      assert.ok(Array.isArray(chart.colors), 'each bubble receives a count color');
      assert.equal(chart.colors.length, chart.sizes.length);
      const filled = chart.colors.filter((_, index) => chart.symbols[index] === 'circle');
      assert.ok(filled.every(color => colors.expectedDotColors.includes(color)), 'filled dots use the three discrete count-band colors');
      chart.sizes.forEach((size, index) => {
        if (chart.id !== 'people' && size === 26 && chart.symbols[index] === 'circle') assert.equal(chart.colors[index], colors.countHigh, 'maximum count uses the high-count color');
        if (chart.symbols[index] === 'circle-open') assert.equal(chart.colors[index], colors.countNeutral, 'zero/unavailable counts stay neutral');
      });
    }
    if (colors.marketColor) assert.equal(colors.marketColor, colors.expectedMarketColor, `${colors.market} uses its own theme-aware market color`);
  }
  const dataSnapshot = page => page.evaluate(() => ({
    charts: [...document.querySelectorAll('.js-plotly-plot')].filter(node => node.data?.length).map(node => ({
      id: node.id, x: node.data[0].x, y: node.data[0].y, ids: node.data[0].ids,
      hover: node.data[0].customdata, sizes: node.data[0].marker.size,
      symbols: node.data[0].marker.symbol, xRange: node.layout.xaxis.range, yRange: node.layout.yaxis.range,
    })),
    role: document.getElementById('people-role').value,
    market: document.getElementById('market').value,
    openDetails: [...document.querySelectorAll('details[open]')].map(node => node.querySelector('summary').textContent),
    people: document.getElementById('people-table').textContent,
    recommendations: document.getElementById('recommendations').textContent,
  }));
  try {
    const { context, page } = await newContext();
    let fetches = 0;
    page.on('request', request => { if (request.url().endsWith('/data/dashboard.json')) fetches++; });
    await page.goto(url);
    await ready(page);
    await themeReady(page, 'dark');
    const button = page.locator('#theme-toggle');
    assert.equal(await button.getAttribute('aria-label'), 'Switch to light mode');
    await page.locator('#market').selectOption('IN');
    await page.locator('#people-role').selectOption('actor');
    await page.locator('#top-movies-table').locator('..').locator('summary').press('Enter');
    const before = await dataSnapshot(page);
    await button.press('Enter');
    await themeReady(page, 'light');
    assert.deepEqual(await dataSnapshot(page), before, 'switching preserves values, scales, hover, bubble sizes, filters and open tables');
    assert.equal(await button.getAttribute('aria-label'), 'Switch to dark mode');
    assert.equal(await page.evaluate(() => localStorage.getItem('movie-observatory-theme')), 'light');
    await button.press('Space');
    await themeReady(page, 'dark');
    assert.deepEqual(await dataSnapshot(page), before);
    assert.equal(fetches, 1, 'theme changes never fetch another data bundle');

    await button.click();
    await themeReady(page, 'light');
    await page.reload();
    await ready(page);
    await themeReady(page, 'light');
    assert.equal(await page.locator('meta[name="theme-color"]').getAttribute('content'), '#f0f2f5');
    await page.locator('#theme-toggle').click();
    await themeReady(page, 'dark');
    await page.reload();
    await ready(page);
    await themeReady(page, 'dark');

    for (const width of [305, 390, 768, 1440, 2560]) {
      await page.setViewportSize({ width, height: 1000 });
      for (const theme of ['light', 'dark']) {
        await page.locator('#theme-toggle').click();
        await themeReady(page, theme);
        assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true, `${width}px ${theme} has no overflow`);
        assert.ok(await page.locator('#theme-toggle').isVisible());
        assert.equal(await page.locator('.chart').count(), 9, 'all nine charts remain present, including empty states');
        if (process.env.SCREENSHOT_DIR && [390, 1440].includes(width)) {
          fs.mkdirSync(process.env.SCREENSHOT_DIR, { recursive: true });
          await page.screenshot({ path: path.join(process.env.SCREENSHOT_DIR, `${width}-${theme}.png`) });
          await page.locator('#top-movies').screenshot({ path: path.join(process.env.SCREENSHOT_DIR, `${width}-${theme}-movies.png`) });
          // The next overview capture starts at the top, rather than the ranking.
          await page.evaluate(() => window.scrollTo(0, 0));
        }
      }
    }
    await context.close();
    const blocked = await newContext(true);
    await blocked.page.goto(url);
    await ready(blocked.page);
    await blocked.page.locator('#theme-toggle').click();
    await themeReady(blocked.page, 'light');
    await blocked.context.close();

    // Exercise exact legend reference values using in-memory responses only.
    // This checks the visible swatch-to-point mapping, not a copy of the color formula.
    const anchors = structuredClone(bundle);
    anchors.top_movies.forEach((row, index) => { row.votes = [1e6, 2e6, 3e6][index % 3]; });
    anchors.eras.top_years.forEach((row, index) => { row.movie_count = [50, 150, 250][index % 3]; });
    anchors.people.forEach((row, index) => { row.movie_count = [4, 5, 6, 7, 8, 10][index % 6]; });
    const references = await newContext(false, anchors);
    await references.page.goto(url);
    await ready(references.page);
    for (const theme of ['dark', 'light']) {
      if (theme === 'light') await references.page.locator('#theme-toggle').click();
      await themeReady(references.page, theme);
      for (const [id, rows, key] of [
        ['top-movies', anchors.top_movies, 'votes'],
        ['top-years', anchors.eras.top_years, 'movie_count'],
        ['people', anchors.people.filter(row => row.role === 'director' && row.rank <= 10), 'movie_count'],
      ]) {
        const matches = await references.page.evaluate(({ id, counts }) => {
          const points = [...document.querySelectorAll(`#${id}-chart .scatterlayer .point`)];
          return [...document.querySelectorAll(`#${id}-size-key .size-key-circle`)].map(swatch => {
            const index = counts.indexOf(Number(swatch.dataset.count));
            return index < 0 || getComputedStyle(points[index]).fill === getComputedStyle(swatch).backgroundColor;
          });
        }, { id, counts: rows.map(row => row[key]) });
        assert.ok(matches.every(Boolean), `${id} rendered legend matches the actual dot fills in ${theme}`);
      }
    }
    await references.context.close();
    assert.deepEqual(errors, []);
    console.log('Theme checks passed: count colors and matching rendered legends, distinct market colors, keyboard toggle, saved preferences, unchanged chart data/filters/tables, no extra fetch, both themes at 305–2560px, and blocked storage.');
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });

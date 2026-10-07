/* Run against a server serving web_dashboard. Uses the existing fixture by
 * default, or an existing bundle via DASHBOARD_FIXTURE. Creates no datasets. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const { chromium } = require('playwright');

async function main() {
  const baseURL = process.env.BASE_URL || 'http://127.0.0.1:8766/';
  const bundle = JSON.parse(fs.readFileSync(process.env.DASHBOARD_FIXTURE || path.join(__dirname, 'fixtures/dashboard/synthetic-dashboard.json'), 'utf8'));
  const browser = await chromium.launch({ headless: true });
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    let responseBundle = bundle;
    await context.route('**/data/dashboard.json', route => route.fulfill({ json: responseBundle }));
    const original = await context.newPage();
    const candidate = await context.newPage();
    const errors = [];
    candidate.on('pageerror', error => errors.push(error.message));
    let fetches = 0;
    candidate.on('request', request => { if (request.url().endsWith('/data/dashboard.json')) fetches++; });
    await original.goto(new URL('index.html', baseURL).href);
    await candidate.goto(new URL('redesign.html', baseURL).href);
    for (const page of [original, candidate]) await page.waitForFunction(() => document.getElementById('load-status').dataset.state === 'ready');
    assert.equal(await candidate.locator('.section-nav [aria-current="location"]').getAttribute('href'), '#overview', 'initial navigation points to visible overview');

    const traceData = page => page.evaluate(() => Object.fromEntries([...document.querySelectorAll('.js-plotly-plot')].filter(node => node.data?.length).map(node => {
      const trace = node.data[0];
      // Compare the complete hover values while allowing the plain-language labels.
      const hoverValues = trace.customdata?.map(value => value
        .replaceAll('Votes (IMDb first):', 'Preferred votes:')
        .replaceAll('Films counted:', node.id === 'people-chart' ? 'Qualifying films:' : 'Qualifying movies:')
        .replaceAll('Movies counted:', 'Qualifying population:')
        .replaceAll('Country:', 'Market:').replaceAll('Release date:', 'Release:')
        .replaceAll('Average movie length (min)', 'Average runtime (min)'));
      const numericAxis = trace.orientation === 'h' || node.id.endsWith('people-chart') || ['top-movies-chart', 'top-years-chart'].includes(node.id) ? 'xaxis' : 'yaxis';
      return [node.id, Object.fromEntries(['type', 'mode', 'orientation', 'x', 'y', 'ids', 'customdata', 'connectgaps', 'hovertemplate'].map(key => [key, key === 'customdata' ? hoverValues : trace[key]]).concat([['range', node.layout[numericAxis].range]]))];
    })));
    assert.deepEqual(await traceData(candidate), await traceData(original), 'all nine traces, numeric scales, rankings and hover values remain unchanged');
    assert.equal(await candidate.locator('.kpi').count(), 4);
    assert.equal(await candidate.locator('.highlight').count(), 2);
    assert.equal(await candidate.locator('.data-disclosure').count(), 9);
    assert.equal(await candidate.locator('#total-movies').textContent(), await original.locator('#total-movies').textContent());
    assert.equal(await candidate.locator('.hero-copy,.hero-meta,.chart-subtitle,.insight-note,.section-note,#catalog-insight,#spotlight-context,#freshness-strip').count(), 0, 'requested repetitive elements are removed, not merely hidden');
    assert.equal(await candidate.locator('details[open]').count(), 0, 'default view prioritizes charts over explanatory prose');
    assert.equal(await candidate.locator('#snapshot-details').isVisible(), false, 'source dates are available on demand');
    await candidate.getByText('Source dates', { exact: true }).click();
    assert.match(await candidate.locator('#snapshot-details').textContent(), /Warehouse completed:.*Bundle exported:.*US capture date:.*India capture date:/s);
    assert.equal(await candidate.locator('#snapshot-details').isVisible(), true);
    await candidate.getByText('Source dates', { exact: true }).click();
    await candidate.locator('#recommendations').locator('..').locator('summary').click();
    assert.equal(await candidate.locator('#recommendations').isVisible(), true, 'movie details remain accessible');
    await candidate.locator('#recommendations').locator('..').locator('summary').click();
    const countColors = new Map();
    async function checkBubbleAreas(id, rows, key, globalRows = rows) {
      const marker = await candidate.locator(`#${id}`).evaluate(node => node.data?.[0]?.marker);
      const plotted = rows.filter(row => Number.isFinite(row.avg_rating ?? row.rating));
      if (!plotted.length) return;
      assert.equal(marker.sizemode, 'diameter');
      assert.equal(marker.size.length, plotted.length);
      const positive = plotted.map((row, index) => ({ count: row[key], diameter: marker.size[index], symbol: marker.symbol[index] })).filter(item => Number.isFinite(item.count) && item.count > 0);
      const maximum = Math.max(...globalRows.map(row => row[key]).filter(Number.isFinite));
      for (const item of positive) {
        assert.equal(item.symbol, 'circle');
        assert.ok(Math.abs((item.diameter / 26) ** 2 - item.count / maximum) < 1e-9, 'filled circle area is proportional to source count, without a minimum-size floor');
      }
      plotted.forEach((row, index) => {
        if (!Number.isFinite(row[key]) || row[key] === 0) assert.equal(marker.symbol[index], 'circle-open', 'unknown/zero counts do not become a positive filled area');
        else {
          const colorKey = `${id}:${row[key]}`;
          if (countColors.has(colorKey)) assert.equal(marker.color[index], countColors.get(colorKey), 'the same count keeps the same color across rows and role selections');
          countColors.set(colorKey, marker.color[index]);
        }
      });
    }
    await checkBubbleAreas('top-movies-chart', bundle.top_movies, 'votes');
    await checkBubbleAreas('top-years-chart', bundle.eras.top_years, 'movie_count');
    assert.match(await candidate.locator('#top-movies-size-key').textContent(), /votes \(IMDb first\)/);
    assert.match(await candidate.locator('#top-years-size-key').textContent(), /films counted/);

    for (const role of await candidate.locator('#people-role option').evaluateAll(options => options.map(option => option.value))) {
      for (const page of [original, candidate]) await page.locator('#people-role').selectOption(role);
      assert.deepEqual((await traceData(candidate))['people-chart'], (await traceData(original))['people-chart'], `unchanged ${role} ranking`);
      assert.equal(await candidate.locator('#people-table').evaluate(node => node.querySelector('tbody')?.textContent || ''), await original.locator('#people-table').evaluate(node => node.querySelector('tbody')?.textContent || ''));
      if (!bundle.people.some(person => person.role === role)) assert.match(await candidate.locator('#people-chart').textContent(), /No values to plot/);
      await checkBubbleAreas('people-chart', bundle.people.filter(person => person.role === role && person.rank <= 10), 'movie_count', bundle.people);
      const peopleBands = await candidate.locator('#people-chart').evaluate(node => {
        if (!node.data?.length) return null;
        const styles = getComputedStyle(node);
        return { colors: node.data[0].marker.color, expected: ['count-low', 'count-mid', 'count-high'].map(token => styles.getPropertyValue(`--${token}`).trim()) };
      });
      const plottedPeople = bundle.people.filter(person => person.role === role && person.rank <= 10 && Number.isFinite(person.avg_rating));
      if (peopleBands) plottedPeople.forEach((person, index) => {
        if (Number.isFinite(person.movie_count) && person.movie_count > 0) {
          assert.equal(peopleBands.colors[index], peopleBands.expected[person.movie_count <= 4 ? 0 : person.movie_count <= 7 ? 1 : 2], `${role}: qualifying-film bands remain 1–4, 5–7 and 8+`);
        }
      });
      if (plottedPeople.length) assert.deepEqual(await candidate.locator('#people-size-key .size-key-band').allTextContents(), ['1–4', '5–7', '8+']);
    }
    const marketColors = [];
    for (const market of ['US', 'IN']) {
      for (const page of [original, candidate]) await page.locator('#market').selectOption(market);
      assert.deepEqual((await traceData(candidate))['now-playing-chart'], (await traceData(original))['now-playing-chart'], `unchanged ${market} recommendations`);
      if (bundle.now_playing.regions[market].recommendations.length) {
        assert.equal((await candidate.locator('#recommendations').textContent()).replaceAll('Votes (IMDb first):', 'Preferred votes:'), await original.locator('#recommendations').textContent());
      } else {
        assert.match(await candidate.locator('#recommendations').textContent(), /No movies meet the recommendation rules/);
        assert.equal(await candidate.locator('#recommendations li').count(), 0);
      }
      const color = await candidate.locator('#now-playing-chart').evaluate(node => node.data?.[0]?.marker.color);
      if (color) marketColors.push(color);
    }
    if (marketColors.length === 2) assert.notEqual(...marketColors, 'US and India have distinct colors');
    for (const page of [original, candidate]) {
      await page.locator('#people-role').selectOption('director');
      await page.locator('#market').selectOption('US');
    }
    const movieValues = bundle.top_movies.map(movie => movie.rating).filter(Number.isFinite);
    assert.equal(await candidate.locator('#movies-title').textContent(), 'Top 10 films of all time');
    assert.equal(await candidate.locator('#years-title').textContent(), 'Top 10 release years by average movie rating');

    // Keyboard users can expose the same values that mouse hover reveals.
    const summary = candidate.locator('#top-movies-table').locator('..').locator('summary');
    await summary.focus();
    await candidate.keyboard.press('Enter');
    assert.equal(await candidate.locator('#top-movies-table table').isVisible(), true);
    const hover = await candidate.evaluate(() => {
      Plotly.Fx.hover('top-movies-chart', [{ curveNumber: 0, pointNumber: 0 }]);
      return document.querySelector('#top-movies-chart .hoverlayer')?.textContent;
    });
    if (movieValues.length) assert.match(hover, /Rank:.*Rating:.*Votes \(IMDb first\):/);

    for (const viewport of [{ width: 390, height: 844 }, { width: 768, height: 1024 }, { width: 1440, height: 1000 }]) {
      await candidate.setViewportSize(viewport);
      await candidate.waitForTimeout(200);
      assert.equal(await candidate.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1), true, `${viewport.width}px has no page overflow`);
      assert.equal(await candidate.locator('.js-plotly-plot').count(), 9);
      assert.deepEqual(await traceData(candidate), await traceData(original), 'responsive recomposition preserves values and scales');
      const crowdedAxes = await candidate.evaluate(() => [...document.querySelectorAll('.js-plotly-plot')].flatMap(node => {
        const boxes = selector => [...node.querySelectorAll(selector)].map(label => label.getBoundingClientRect());
        const xTicks = boxes('.xtick text');
        const yTicks = boxes('.ytick text');
        const overlaps = xTicks.some(x => yTicks.some(y => x.left < y.right && x.right > y.left && x.top < y.bottom && x.bottom > y.top));
        const horizontal = node.data[0].orientation === 'h' || node.data[0].mode === 'markers+text';
        const bottomGap = horizontal && xTicks.length && yTicks.length
          ? Math.min(...xTicks.map(box => box.top)) - Math.max(...yTicks.map(box => box.bottom)) : Infinity;
        const sideGap = xTicks.length && yTicks.length
          ? Math.min(...xTicks.map(box => box.left)) - Math.max(...yTicks.map(box => box.right)) : Infinity;
        return overlaps || bottomGap < 32 || sideGap < (innerWidth <= 720 ? 14 : 40) ? [node.id] : [];
      }));
      assert.deepEqual(crowdedAxes, [], `${viewport.width}px: axes remain distinct, with room below the final category label`);
    }
    assert.equal(fetches, 1, 'role, market and responsive interactions reuse the same bundle');
    if (bundle.top_movies.length >= 2) {
      responseBundle = structuredClone(bundle);
      responseBundle.top_movies[0].votes = null;
      responseBundle.top_movies[1].votes = 0;
      await candidate.reload();
      await candidate.waitForFunction(() => document.getElementById('load-status').dataset.state === 'ready');
      assert.deepEqual(await candidate.locator('#top-movies-chart').evaluate(node => node.data[0].marker.symbol.slice(0, 2)), ['circle-open', 'circle-open']);
      assert.match(await candidate.locator('#top-movies-size-key').textContent(), /zero or unavailable counts/);
      const hoverValues = await candidate.locator('#top-movies-chart').evaluate(node => node.data[0].customdata);
      assert.match(hoverValues[0], /Votes \(IMDb first\): Unavailable/);
      assert.match(hoverValues[1], /Votes \(IMDb first\): 0/);
    }
    // Shared leaders may change on the next snapshot; test every presentation
    // branch with in-memory responses, never with a new exported dataset.
    const highlightMovie = bundle.overview.highest_rated_movie;
    if (highlightMovie) {
      async function reloadHighlights(rated, voted) {
        responseBundle = structuredClone(bundle);
        responseBundle.overview.highest_rated_movie = rated;
        responseBundle.overview.most_voted_movie = voted;
        await candidate.reload();
        await candidate.waitForFunction(() => document.getElementById('load-status').dataset.state === 'ready');
      }
      await reloadHighlights(highlightMovie, highlightMovie);
      assert.equal(await candidate.locator('#movie-spotlight').getAttribute('data-shared-leader'), 'true');
      assert.equal(await candidate.locator('#spotlight-title').textContent(), highlightMovie.title);
      assert.equal(await candidate.locator('.spotlight-movie').count(), 0, 'shared movie title appears once');
      assert.doesNotMatch(await candidate.locator('#highest-rated').textContent(), /preferred votes/, 'rating highlight does not repeat vote metric');
      assert.doesNotMatch(await candidate.locator('#most-voted').textContent(), /\/ 10/, 'vote highlight does not repeat rating metric');
      await candidate.locator('.spotlight-link').focus();
      await candidate.keyboard.press('Enter');
      assert.equal(await candidate.locator('#top-movies').evaluate(node => node === document.activeElement), true, 'ranking link transfers keyboard focus');
      await reloadHighlights(highlightMovie, { ...highlightMovie, movie_id: 'different-test-id', title: '<img src=x onerror=alert(1)> Independent leader' });
      assert.equal(await candidate.locator('#movie-spotlight').getAttribute('data-shared-leader'), 'false');
      assert.equal(await candidate.locator('.spotlight-movie').count(), 2);
      assert.equal(await candidate.locator('#movie-spotlight img').count(), 0, 'movie source titles are literal text');
      assert.match(await candidate.locator('#most-voted').textContent(), /Independent leader/);
      await reloadHighlights({ ...highlightMovie, movie_id: null }, { ...highlightMovie, movie_id: null });
      assert.equal(await candidate.locator('#movie-spotlight').getAttribute('data-shared-leader'), 'false', 'missing IDs cannot prove shared identity');
      await reloadHighlights({ ...highlightMovie, rating: null }, null);
      assert.match(await candidate.locator('#highest-rated').textContent(), /Unavailable/);
      assert.match(await candidate.locator('#most-voted').textContent(), /No movie meets/);
      await reloadHighlights(null, null);
      assert.equal(await candidate.locator('#movie-spotlight .empty-state').count(), 2);
    }
    // Equal rounded percentages need not represent equal bin counts.
    if (bundle.ratings.bins.length >= 2) {
      responseBundle = structuredClone(bundle);
      responseBundle.ratings.population_count = 20001;
      responseBundle.ratings.bins = responseBundle.ratings.bins.slice(0, 2).map((bin, index) => ({ ...bin, movie_count: 10000 + index, percentage: 50 }));
      await candidate.reload();
      await candidate.waitForFunction(() => document.getElementById('load-status').dataset.state === 'ready');
      const colors = await candidate.locator('#histogram-chart').evaluate(node => node.data[0].marker.color);
      const teal = await candidate.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--green').trim());
      assert.equal(colors.filter(color => color === teal).length, 1, 'emphasis uses raw counts, not rounded percentages');
      assert.equal(colors[responseBundle.ratings.bins[1].order], teal);
    }
    assert.deepEqual(errors, []);
    console.log('Comparison passed: identical chart data/scales/hover; count-proportional bubble areas; every role and market; simplified default view; on-demand source dates and movie details; shared/different/missing leaders; keyboard links/disclosure; mobile/tablet/desktop; one data fetch.');
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });

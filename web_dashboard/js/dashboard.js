/* Public contract v1. This page fetches one atomic, validated bundle. */
(() => {
  'use strict';

  const DAY = 86_400_000;
  const integer = new Intl.NumberFormat('en-US');
  const decimal = new Intl.NumberFormat('en-US', { minimumFractionDigits: 1, maximumFractionDigits: 2 });
  const dateFormat = new Intl.DateTimeFormat('en-US', { year: 'numeric', month: 'short', day: 'numeric', timeZone: 'UTC' });
  const timeFormat = new Intl.DateTimeFormat('en-US', { year: 'numeric', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', timeZone: 'UTC', timeZoneName: 'short' });
  const roles = [
    ['actor', 'Actor', 5], ['actress', 'Actress', 5], ['director', 'Director', 3],
    ['writer', 'Writer', 4], ['producer', 'Producer', 4], ['cinematographer', 'Cinematographer', 4],
    ['composer', 'Composer', 4], ['editor', 'Editor', 5], ['production_designer', 'Production designer', 4],
    ['casting_director', 'Casting director', 5], ['archive_footage', 'Archive footage', 5],
  ];
  const markets = { US: 'United States', IN: 'India' };
  const metricLabels = {
    overview: 'Catalog overview', ratings: 'Rating distribution', genres: 'Genres', eras: 'Eras',
    top_movies: 'Top movies', people: 'People', now_playing: 'Now playing',
  };
  const $ = id => document.getElementById(id);
  const number = (value, precise = false) => value == null ? 'Unavailable' : (precise ? decimal : integer).format(value);
  const text = value => value == null || value === '' ? 'Unavailable' : String(value);
  const date = value => dateFormat.format(new Date(`${value}T00:00:00Z`));
  // Plotly interprets selected HTML tags in labels. Escape source values before
  // passing them into ANY Plotly text, tick label or hover field.
  const plotText = value => text(value).replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#39;');
  const shortLabel = value => value.length > 26 ? `${value.slice(0, 25)}…` : value;

  function element(tag, content, className) {
    const node = document.createElement(tag);
    if (content !== undefined) node.textContent = content;
    if (className) node.className = className;
    return node;
  }

  function empty(target, message) {
    $(target).replaceChildren(element('p', message, 'empty-state'));
  }

  function table(target, caption, columns, rows, emptyMessage = 'No qualifying records in this snapshot.') {
    const container = $(target);
    if (!rows.length) return empty(target, emptyMessage);
    const wrapper = element('div', undefined, 'table-wrap');
    const result = element('table');
    result.append(element('caption', caption));
    const head = element('thead');
    const headings = element('tr');
    for (const column of columns) {
      const cell = element('th', column.label, column.className);
      cell.scope = 'col';
      headings.append(cell);
    }
    head.append(headings);
    const body = element('tbody');
    for (const row of rows) {
      const tr = element('tr');
      columns.forEach(column => {
        const cell = element(column.rowHeader ? 'th' : 'td', column.format ? column.format(row[column.key]) : text(row[column.key]), column.className);
        if (column.rowHeader) cell.scope = 'row';
        tr.append(cell);
      });
      body.append(tr);
    }
    result.append(head, body);
    wrapper.append(result);
    container.replaceChildren(wrapper);
  }

  function isObject(value) { return value !== null && typeof value === 'object' && !Array.isArray(value); }
  function requireValue(condition) { if (!condition) throw new Error('Invalid dashboard bundle.'); }
  function calendarDate(value) {
    requireValue(typeof value === 'string' && /^\d{4}-\d{2}-\d{2}$/.test(value));
    const parsed = new Date(`${value}T00:00:00Z`);
    requireValue(Number.isFinite(parsed.getTime()) && parsed.toISOString().slice(0, 10) === value);
  }
  function timestamp(value) {
    requireValue(typeof value === 'string' && /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z$/.test(value));
    requireValue(Number.isFinite(Date.parse(value)));
    calendarDate(value.slice(0, 10));
  }
  function validateBundle(bundle) {
    requireValue(isObject(bundle));
    if (bundle.schema_version !== 1) {
      const error = new Error('Unsupported data version');
      error.code = 'UNSUPPORTED_VERSION';
      throw error;
    }
    for (const key of ['metadata', 'overview', 'ratings', 'genres', 'eras', 'now_playing']) requireValue(isObject(bundle[key]));
    const { metadata, overview, ratings, genres, eras, now_playing: current } = bundle;
    timestamp(metadata.warehouse_completed_at);
    timestamp(metadata.exported_at);
    requireValue(isObject(metadata.tmdb_capture_dates) && isObject(metadata.metric_definitions));
    requireValue(typeof metadata.synthetic === 'boolean' && metadata.imdb_capture_date === null);
    requireValue(Array.isArray(metadata.limitations) && metadata.limitations.every(value => typeof value === 'string'));
    for (const key of Object.keys(metricLabels)) requireValue(typeof metadata.metric_definitions[key] === 'string');
    for (const key of ['total_movies', 'rated_movies']) requireValue(Number.isInteger(overview[key]) && overview[key] >= 0);
    for (const key of ['avg_rating', 'avg_runtime_minutes']) requireValue(overview[key] === null || Number.isFinite(overview[key]));
    for (const value of [ratings.bins, genres.ratings, genres.runtimes, eras.counts, eras.ratings, eras.top_years, bundle.top_movies, bundle.people]) requireValue(Array.isArray(value));
    requireValue(Number.isInteger(ratings.population_count) && ratings.population_count >= 0 && isObject(current.regions));
    for (const market of Object.keys(markets)) {
      calendarDate(metadata.tmdb_capture_dates[market]);
      const region = current.regions[market];
      requireValue(isObject(region) && Number.isInteger(region.movie_count) && region.movie_count >= 0 && Array.isArray(region.recommendations));
    }
    // The exporter owns complete JSON Schema and semantic validation. These
    // shape checks let this static client fail clearly on missing/invalid data.
    return bundle;
  }

  function freshness(metadata) {
    const now = Date.now();
    const today = new Date(now);
    const utcDay = Date.UTC(today.getUTCFullYear(), today.getUTCMonth(), today.getUTCDate());
    const stale = [];
    if (now - Date.parse(metadata.warehouse_completed_at) > 8 * DAY) stale.push('warehouse build');
    for (const market of Object.keys(markets)) {
      if (utcDay - Date.parse(`${metadata.tmdb_capture_dates[market]}T00:00:00Z`) > 8 * DAY) stale.push(`${markets[market]} capture`);
    }
    if (stale.length) {
      $('freshness-notice').textContent = `Stale data — ${stale.join(' and ')} is more than eight days old. The most recent available snapshot is shown below.`;
      $('freshness-notice').hidden = false;
    }
    $('synthetic-notice').hidden = !metadata.synthetic;
    const strip = $('freshness-strip');
    const build = element('span');
    build.append(element('strong', 'Warehouse built '), document.createTextNode(timeFormat.format(new Date(metadata.warehouse_completed_at))));
    strip.append(build, element('span', `TMDB capture: US ${date(metadata.tmdb_capture_dates.US)} · India ${date(metadata.tmdb_capture_dates.IN)}`));
    const details = $('snapshot-details');
    for (const line of [
      `Warehouse completed: ${timeFormat.format(new Date(metadata.warehouse_completed_at))}`,
      `Bundle exported: ${timeFormat.format(new Date(metadata.exported_at))}`,
      `US capture date: ${date(metadata.tmdb_capture_dates.US)}`,
      `India capture date: ${date(metadata.tmdb_capture_dates.IN)}`,
      'IMDb capture date: Unavailable',
    ]) details.append(element('p', line));
  }

  function metric(target, value, unit) {
    const node = $(target);
    if (value === null) return node.append(element('span', 'Unavailable', 'unavailable'));
    node.append(document.createTextNode(number(value, Boolean(unit))));
    if (unit) node.append(element('span', unit, 'kpi-unit'));
  }

  function highlight(target, movie) {
    if (!movie) return empty(target, 'No qualifying movie in this snapshot.');
    const metrics = element('p', undefined, 'highlight-metrics');
    const rating = element('span');
    rating.append(element('strong', number(movie.rating, true)), document.createTextNode(movie.rating == null ? ' rating' : ' / 10'));
    const votes = element('span');
    votes.append(element('strong', number(movie.votes)), document.createTextNode(' preferred votes'));
    metrics.append(rating, votes);
    $(target).append(element('h3', text(movie.title)), metrics);
  }

  function plot(target, rows, labelKey, valueKey, { horizontal = false, rating = false, unit = 'movies', percentKey, color = '#557969' } = {}) {
    const node = $(target);
    const available = rows.filter(row => row[valueKey] !== null);
    if (!available.length) {
      node.classList.add('chart-empty');
      node.textContent = 'No qualifying data for this chart. The table below includes any unavailable values.';
      return;
    }
    if (!window.Plotly) {
      node.classList.add('chart-empty');
      node.textContent = 'The chart library could not load. All values are available in the data table below.';
      return;
    }
    const categories = available.map((_, index) => index);
    const values = available.map(row => row[valueKey]);
    const labels = available.map(row => plotText(row[labelKey]));
    const tickLabels = available.map(row => plotText(horizontal ? shortLabel(row[labelKey]) : row[labelKey]));
    const trace = {
      type: 'bar', orientation: horizontal ? 'h' : 'v',
      x: horizontal ? values : categories, y: horizontal ? categories : values,
      marker: { color, line: { width: 0 } }, text: labels,
      customdata: available.map(row => percentKey ? number(row[percentKey], true) : ''),
      hovertemplate: `%{text}<br>%{${horizontal ? 'x' : 'y'}:,.${rating ? '2' : '0'}f} ${unit}${percentKey ? '<br>%{customdata}% of qualifying titles' : ''}<extra></extra>`,
    };
    const categorical = { tickvals: categories, ticktext: tickLabels, fixedrange: true, showgrid: false, zeroline: false, tickfont: { size: horizontal ? 10 : 11 }, automargin: true };
    const numerical = { fixedrange: true, gridcolor: '#e5e6dc', zeroline: false, rangemode: 'tozero', title: { text: unit, font: { size: 10, color: '#5d6863' }, standoff: 12 }, ...(rating ? { range: [0, 10] } : {}), automargin: true };
    if (horizontal) categorical.autorange = 'reversed';
    const height = horizontal ? Math.max(280, Math.min(960, available.length * 30 + 65)) : 290;
    node.style.height = `${height}px`;
    return window.Plotly.newPlot(node, [trace], {
      autosize: true, height, paper_bgcolor: '#fffefa', plot_bgcolor: '#fffefa',
      font: { family: 'Arial, sans-serif', color: '#5d6863', size: 11 },
      margin: { t: 18, b: 48, l: horizontal ? 130 : 52, r: 12 },
      bargap: horizontal ? .32 : .24, showlegend: false,
      xaxis: horizontal ? numerical : categorical, yaxis: horizontal ? categorical : numerical,
      hoverlabel: { bgcolor: '#192524', bordercolor: '#192524', font: { color: '#fffefa', size: 12 } },
    }, { responsive: true, displayModeBar: false, scrollZoom: false, doubleClick: false, showTips: false }).catch(() => {
      node.replaceChildren();
      node.classList.add('chart-empty');
      node.textContent = 'This chart could not render. All values are available in the data table below.';
    });
  }

  function renderCharts(bundle) {
    const histogram = [...bundle.ratings.bins].sort((a, b) => a.order - b.order);
    const histogramPopulation = $('histogram-population');
    histogramPopulation.append(element('strong', number(bundle.ratings.population_count)), document.createTextNode('qualifying movies'));
    const chartTasks = [plot('histogram-chart', histogram, 'bracket', 'movie_count', { percentKey: 'percentage' })];
    table('histogram-table', 'Rating distribution · qualifying population', [
      { key: 'bracket', label: 'Rating bracket', rowHeader: true },
      { key: 'movie_count', label: 'Movies', className: 'numeric', format: number },
      { key: 'percentage', label: 'Share', className: 'numeric', format: value => `${number(value, true)}%` },
    ], histogram, 'No qualifying movies for the rating distribution.');
    for (const definition of [
      { id: 'genre-ratings', rows: bundle.genres.ratings, label: 'genre', value: 'avg_rating', heading: 'Genre', metric: 'Mean rating / 10', rating: true, unit: 'rating / 10', horizontal: true },
      { id: 'genre-runtimes', rows: bundle.genres.runtimes, label: 'genre', value: 'avg_runtime_minutes', heading: 'Genre', metric: 'Mean minutes', unit: 'minutes', horizontal: true, color: '#bf805b' },
      { id: 'decade-counts', rows: bundle.eras.counts, label: 'decade', value: 'movie_count', heading: 'Decade', metric: 'Qualifying movies', unit: 'movies' },
      { id: 'decade-ratings', rows: bundle.eras.ratings, label: 'decade', value: 'avg_rating', heading: 'Decade', metric: 'Mean rating / 10', rating: true, unit: 'rating / 10', color: '#bf805b' },
    ]) {
      chartTasks.push(plot(`${definition.id}-chart`, definition.rows, definition.label, definition.value, definition));
      table(`${definition.id}-table`, definition.metric, [
        { key: definition.label, label: definition.heading, rowHeader: true },
        { key: definition.value, label: definition.metric, className: 'numeric', format: value => number(value, definition.value !== 'movie_count') },
      ], definition.rows);
    }
    return chartTasks;
  }

  function renderRankings(bundle) {
    table('top-movies-table', 'Top movies · 100,000+ votes on either source', [
      { key: 'rank', label: 'Rank', className: 'rank-cell', format: number },
      { key: 'title', label: 'Movie', className: 'title-cell', rowHeader: true },
      { key: 'rating', label: 'Rating / 10', className: 'numeric', format: value => number(value, true) },
      { key: 'votes', label: 'Preferred votes', className: 'numeric', format: number },
    ], bundle.top_movies, 'No movies qualify for the top movie ranking.');
    table('top-years-table', 'Top release years · at least five qualifying films per year', [
      { key: 'rank', label: 'Rank', className: 'rank-cell', format: number },
      { key: 'year', label: 'Release year', rowHeader: true },
      { key: 'avg_rating', label: 'Mean rating / 10', className: 'numeric', format: value => number(value, true) },
      { key: 'movie_count', label: 'Qualifying films', className: 'numeric', format: number },
    ], bundle.eras.top_years, 'No release years qualify for this ranking.');
  }

  function renderPeople(bundle) {
    const select = $('people-role');
    for (const [value, label] of roles) {
      const option = element('option', label);
      option.value = value;
      select.append(option);
    }
    function update() {
      const [, label, minimum] = roles.find(role => role[0] === select.value);
      $('people-threshold').textContent = `${label}: at least ${minimum} distinct qualifying films represented in principal credits.`;
      table('people-table', `${label} · up to 20 people`, [
        { key: 'rank', label: 'Rank', className: 'rank-cell', format: number },
        { key: 'name', label: 'Name', className: 'title-cell', rowHeader: true },
        { key: 'movie_count', label: 'Qualifying films', className: 'numeric', format: number },
        { key: 'avg_rating', label: 'Mean rating / 10', className: 'numeric', format: value => number(value, true) },
      ], bundle.people.filter(person => person.role === select.value), 'No people qualify for this role in the current snapshot.');
    }
    select.addEventListener('change', update);
    update();
  }

  function renderMarkets(bundle) {
    const select = $('market');
    const counts = $('market-counts');
    for (const market of Object.keys(markets)) {
      const count = element('div', undefined, 'market-count');
      count.dataset.market = market;
      count.append(element('span', `${markets[market]} · titles`), element('strong', number(bundle.now_playing.regions[market].movie_count)));
      counts.append(count);
    }
    function update() {
      const market = select.value;
      const region = bundle.now_playing.regions[market];
      for (const node of counts.children) node.classList.toggle('is-selected', node.dataset.market === market);
      $('market-snapshot').textContent = `${markets[market]} snapshot captured ${date(bundle.metadata.tmdb_capture_dates[market])}. Exhibition market does not indicate a movie’s nationality.`;
      const container = $('recommendations');
      if (!region.recommendations.length) return empty('recommendations', 'No recommendations qualify for this market in the current snapshot.');
      const list = element('ol', undefined, 'recommendation-list');
      for (const movie of region.recommendations) {
        const item = element('li', undefined, 'recommendation');
        const rank = element('span', String(movie.rank).padStart(2, '0'), 'recommendation-rank');
        rank.setAttribute('aria-label', `Rank ${movie.rank}`);
        const content = element('div');
        content.append(element('h4', text(movie.title)));
        content.append(element('p', `Rating: ${number(movie.rating, true)}${movie.rating === null ? '' : ' / 10'} · Preferred votes: ${number(movie.votes)} · TMDB popularity: ${number(movie.popularity, true)} · Release: ${movie.release_date === null ? 'Unavailable' : date(movie.release_date)}`, 'recommendation-meta'));
        content.append(element('p', movie.overview == null || movie.overview === '' ? 'Synopsis unavailable.' : movie.overview, 'recommendation-overview'));
        item.append(rank, content);
        list.append(item);
      }
      container.replaceChildren(list);
    }
    select.addEventListener('change', update);
    update();
  }

  async function render(bundle) {
    freshness(bundle.metadata);
    metric('total-movies', bundle.overview.total_movies);
    metric('rated-movies', bundle.overview.rated_movies);
    metric('average-rating', bundle.overview.avg_rating, '/ 10');
    metric('average-runtime', bundle.overview.avg_runtime_minutes, 'min');
    highlight('highest-rated', bundle.overview.highest_rated_movie);
    highlight('most-voted', bundle.overview.most_voted_movie);
    renderRankings(bundle);
    renderPeople(bundle);
    renderMarkets(bundle);
    for (const [key, label] of Object.entries(metricLabels)) {
      $('metric-definitions').append(element('dt', label), element('dd', bundle.metadata.metric_definitions[key]));
    }
    for (const limitation of bundle.metadata.limitations) $('limitations').append(element('li', limitation));
    // Plotly must see a laid-out container to size its responsive SVG correctly.
    $('dashboard').hidden = false;
    await Promise.all(renderCharts(bundle));
    $('load-status').textContent = 'Snapshot loaded. Source and build dates are shown below.';
    $('load-status').dataset.state = 'ready';
  }

  async function load() {
    try {
      const response = await fetch('data/dashboard.json', { cache: 'no-cache', credentials: 'omit' });
      if (!response.ok) throw new Error(`Bundle request failed (${response.status}).`);
      await render(validateBundle(await response.json()));
    } catch (error) {
      $('dashboard').hidden = true;
      const status = $('load-status');
      status.dataset.state = 'error';
      status.textContent = error.code === 'UNSUPPORTED_VERSION'
        ? 'This dashboard received an unsupported data version. Please reload after the site has been updated.'
        : 'The movie snapshot could not be loaded. Please try reloading later. No sample values have been substituted.';
    }
  }
  load();
})();

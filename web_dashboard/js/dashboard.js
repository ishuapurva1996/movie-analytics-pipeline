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
  const shortLabel = value => {
    const label = text(value);
    return label.length > 26 ? `${label.slice(0, 25)}…` : label;
  };
  const fixed = (value, digits = 2) => value == null ? 'Unavailable' : value.toFixed(digits);
  function ratingRange(rows, key, initial, padding = .1) {
    const values = rows.map(row => row[key]).filter(Number.isFinite);
    return [Math.max(0, Math.min(initial[0], ...values.map(value => Math.floor((value - padding) * 2) / 2))),
      Math.min(10, Math.max(initial[1], ...values.map(value => Math.ceil((value + padding) * 2) / 2)))];
  }
  const movieHover = row => `${plotText(row.title)}<br>Rank: ${row.rank}<br>Rating: ${fixed(row.rating)} / 10<br>Preferred votes: ${number(row.votes)}`;

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
    node.append(document.createTextNode(unit ? fixed(value, unit === 'min' ? 1 : 2) : number(value)));
    if (unit) node.append(element('span', unit, 'kpi-unit'));
  }

  function highlight(target, movie) {
    if (!movie) return empty(target, 'No qualifying movie in this snapshot.');
    const metrics = element('p', undefined, 'highlight-metrics');
    const rating = element('span');
    rating.append(element('strong', number(movie.rating, true)), document.createTextNode(movie.rating == null ? ' rating' : ' / 10'));
    const votes = element('span');
    votes.append(element('strong', number(movie.votes)), document.createTextNode(' preferred votes'));
    metrics.append(...(target === 'most-voted' ? [votes, rating] : [rating, votes]));
    $(target).append(element('h3', text(movie.title)), metrics);
  }

  function plot(target, rows, labelKey, valueKey, { horizontal = false, rating = false, unit = 'movies', color = '#557969', kind = 'bar', range, hover, idKey, digits = rating ? 2 : 0 } = {}) {
    const node = $(target);
    const available = rows.filter(row => Number.isFinite(row[valueKey]));
    function fallback(message) {
      if (window.Plotly && node.data) window.Plotly.purge(node);
      node.replaceChildren();
      node.style.height = '';
      node.classList.add('chart-empty');
      node.textContent = message;
    }
    if (!available.length) return fallback('No qualifying data for this chart. The data below includes any unavailable values.');
    if (!window.Plotly) return fallback('The chart library could not load. All values are available in the data below.');
    node.classList.remove('chart-empty');
    // Keep explicit nulls in decade traces: a missing decade is a gap, never zero.
    const plotted = kind === 'line' || target === 'decade-counts-chart' ? rows : available;
    const categories = plotted.map((row, index) => kind === 'line' || target === 'decade-counts-chart' ? parseInt(row[labelKey], 10) : index);
    const values = plotted.map(row => row[valueKey]);
    const labels = plotted.map(row => plotText(row[labelKey]));
    const tickLabels = plotted.map(row => plotText(horizontal ? shortLabel(row[labelKey]) : row[labelKey]));
    const trace = {
      type: kind === 'bar' ? 'bar' : 'scatter',
      ...(kind === 'bar' ? { orientation: horizontal ? 'h' : 'v' } : { mode: kind === 'line' ? 'lines+markers' : 'markers+text', connectgaps: false, line: { color, width: 2, shape: 'linear' } }),
      x: horizontal ? values : categories, y: horizontal ? categories : values,
      ...(idKey ? { ids: plotted.map(row => String(row[idKey])) } : {}),
      marker: { color, size: 9, line: { width: 0 } },
      ...(horizontal ? { text: values.map(value => fixed(value, digits)), textposition: kind === 'dot' ? 'middle right' : 'outside', cliponaxis: false } : {}),
      customdata: plotted.map((row, index) => hover ? hover(row) : `${labels[index]}<br>${fixed(row[valueKey], digits)} ${unit}`),
      hovertemplate: '%{customdata}<extra></extra>',
    };
    const categorical = { tickvals: categories, ticktext: tickLabels, fixedrange: true, showgrid: false, zeroline: false, tickfont: { size: 11 }, automargin: true };
    const numerical = { fixedrange: true, gridcolor: '#e5e6dc', zeroline: false, rangemode: 'tozero', title: { text: unit, font: { size: 11, color: '#5d6863' }, standoff: 12 }, ...(range ? { range } : rating ? { range: [0, 10] } : {}), automargin: true };
    if (!rating && !digits) numerical.tickformat = ',.0f';
    if (horizontal) categorical.range = [plotted.length - .5, -.5];
    if (target.startsWith('decade-')) categorical.tickangle = -35;
    const height = horizontal ? Math.max(280, plotted.length * 32 + 70) : 310;
    node.style.height = `${height}px`;
    const layout = {
      autosize: true, height, paper_bgcolor: '#fffefa', plot_bgcolor: '#fffefa',
      font: { family: 'Arial, sans-serif', color: '#5d6863', size: 11 },
      margin: { t: 18, b: 55, l: horizontal ? 150 : 55, r: horizontal ? 55 : 15 },
      bargap: target === 'histogram-chart' ? .04 : horizontal ? .32 : .24, showlegend: false,
      xaxis: horizontal ? numerical : categorical, yaxis: horizontal ? categorical : numerical,
      hoverlabel: { bgcolor: '#192524', bordercolor: '#192524', font: { color: '#fffefa', size: 12 } },
    };
    const config = { responsive: true, displayModeBar: false, scrollZoom: false, doubleClick: false, showTips: false };
    const draw = node.data ? window.Plotly.react : window.Plotly.newPlot;
    return draw(node, [trace], layout, config).catch(() => fallback('This chart could not render. All values are available in the data below.'));
  }

  function renderCharts(bundle) {
    const histogram = bundle.ratings.population_count ? Array.from({ length: 10 }, (_, order) =>
      bundle.ratings.bins.find(bin => bin.order === order) || { bracket: `${order}-${order + 1}`, order, movie_count: 0, percentage: 0 }) : [];
    $('histogram-population').append(element('strong', number(bundle.ratings.population_count)), document.createTextNode('qualifying movies'));
    const chartTasks = [plot('histogram-chart', histogram, 'bracket', 'percentage', {
      unit: 'Qualifying movies (%)', digits: 2,
      hover: row => `${plotText(row.bracket)}<br>Movies: ${number(row.movie_count)}<br>Share: ${fixed(row.percentage)}%<br>Qualifying population: ${number(bundle.ratings.population_count)}`,
    })];
    table('histogram-table', 'Rating distribution · qualifying population', [
      { key: 'bracket', label: 'Rating bracket', rowHeader: true },
      { key: 'movie_count', label: 'Movies', className: 'numeric', format: number },
      { key: 'percentage', label: 'Share', className: 'numeric', format: value => `${number(value, true)}%` },
    ], histogram, 'No qualifying movies for the rating distribution.');
    const byMetric = (rows, key) => [...rows].sort((a, b) => (b[key] ?? -Infinity) - (a[key] ?? -Infinity) || a.genre.localeCompare(b.genre));
    const decades = (rows, key) => rows.length ? Array.from({ length: 14 }, (_, index) => {
      const decade = `${1890 + index * 10}s`;
      return rows.find(row => row.decade === decade) || { decade, [key]: null };
    }) : [];
    for (const definition of [
      { id: 'genre-ratings', rows: byMetric(bundle.genres.ratings, 'avg_rating'), label: 'genre', value: 'avg_rating', heading: 'Genre', metric: 'Mean rating / 10', rating: true, unit: 'Average movie rating (/10)', horizontal: true },
      { id: 'genre-runtimes', rows: byMetric(bundle.genres.runtimes, 'avg_runtime_minutes'), label: 'genre', value: 'avg_runtime_minutes', heading: 'Genre', metric: 'Mean minutes', unit: 'Average runtime (min)', digits: 1, horizontal: true, color: '#bf805b' },
      { id: 'decade-counts', rows: decades(bundle.eras.counts, 'movie_count'), label: 'decade', value: 'movie_count', heading: 'Decade', metric: 'Qualifying movies', unit: 'Movies in catalog', hover: row => `${plotText(row.decade)}<br>Movies: ${number(row.movie_count)}${row.decade === '2020s' ? '<br>Incomplete decade' : ''}` },
      { id: 'decade-ratings', rows: decades(bundle.eras.ratings, 'avg_rating'), label: 'decade', value: 'avg_rating', heading: 'Decade', metric: 'Mean rating / 10', kind: 'line', rating: true, range: ratingRange(bundle.eras.ratings, 'avg_rating', [10, 0], .5), unit: 'Average movie rating (/10)', color: '#bf805b', hover: row => `${plotText(row.decade)}<br>Average rating: ${fixed(row.avg_rating)} / 10${row.decade === '2020s' ? '<br>Incomplete decade' : ''}` },
    ]) {
      chartTasks.push(plot(`${definition.id}-chart`, definition.rows, definition.label, definition.value, definition));
      table(`${definition.id}-table`, definition.metric, [
        { key: definition.label, label: definition.heading, rowHeader: true },
        { key: definition.value, label: definition.metric, className: 'numeric', format: value => definition.value === 'movie_count' ? number(value) : fixed(value, definition.value === 'avg_runtime_minutes' ? 1 : 2) },
      ], definition.rows);
    }
    chartTasks.push(plot('top-movies-chart', bundle.top_movies, 'title', 'rating', {
      horizontal: true, rating: true, kind: 'dot', range: ratingRange(bundle.top_movies, 'rating', [8, 10]), unit: 'Movie rating (/10)', hover: movieHover, idKey: 'movie_id',
    }));
    chartTasks.push(plot('top-years-chart', bundle.eras.top_years, 'year', 'avg_rating', {
      horizontal: true, rating: true, kind: 'dot', range: ratingRange(bundle.eras.top_years, 'avg_rating', [6.5, 7]), unit: 'Average movie rating (/10)',
      hover: row => `${row.year}<br>Rank: ${row.rank}<br>Average rating: ${fixed(row.avg_rating)} / 10<br>Qualifying movies: ${number(row.movie_count)}`,
    }));
    return chartTasks;
  }

  function renderRankings(bundle) {
    table('top-movies-table', 'Top movies · 100,000+ votes on either source', [
      { key: 'rank', label: 'Rank', className: 'rank-cell', format: number },
      { key: 'title', label: 'Movie', className: 'title-cell', rowHeader: true },
      { key: 'rating', label: 'Rating / 10', className: 'numeric', format: value => fixed(value) },
      { key: 'votes', label: 'Preferred votes', className: 'numeric', format: number },
    ], bundle.top_movies, 'No movies qualify for the top movie ranking.');
    table('top-years-table', 'Top release years · at least five qualifying films per year', [
      { key: 'rank', label: 'Rank', className: 'rank-cell', format: number },
      { key: 'year', label: 'Release year', rowHeader: true },
      { key: 'avg_rating', label: 'Mean rating / 10', className: 'numeric', format: value => fixed(value) },
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
    select.value = 'director';
    const range = ratingRange(bundle.people, 'avg_rating', [7, 9]);
    function update() {
      const [, label, minimum] = roles.find(role => role[0] === select.value);
      $('people-threshold').textContent = `${label}: at least ${minimum} distinct qualifying films represented in principal credits.`;
      const people = bundle.people.filter(person => person.role === select.value);
      $('people-chart-title').textContent = `Top 10 · ${label}`;
      const chart = plot('people-chart', people.filter(person => person.rank <= 10), 'name', 'avg_rating', {
        horizontal: true, rating: true, kind: 'dot', range, unit: 'Average movie rating (/10)', idKey: 'person_id',
        hover: row => `${plotText(row.name)}<br>Role: ${plotText(label)}<br>Rank: ${row.rank}<br>Average movie rating: ${fixed(row.avg_rating)} / 10<br>Qualifying films: ${number(row.movie_count)}`,
      });
      table('people-table', `${label} · up to 20 people`, [
        { key: 'rank', label: 'Rank', className: 'rank-cell', format: number },
        { key: 'name', label: 'Name', className: 'title-cell', rowHeader: true },
        { key: 'movie_count', label: 'Qualifying films', className: 'numeric', format: number },
        { key: 'avg_rating', label: 'Mean rating / 10', className: 'numeric', format: value => fixed(value) },
      ], people, 'No people qualify for this role in the current snapshot.');
      return chart;
    }
    select.addEventListener('change', update);
    return update();
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
      $('now-playing-chart-title').textContent = `Top 5 · ${markets[market]}`;
      const chart = plot('now-playing-chart', region.recommendations, 'title', 'rating', {
        horizontal: true, rating: true, unit: 'Movie rating (/10)', idKey: 'movie_id',
        hover: row => `${movieHover(row)}<br>Market: ${markets[market]}<br>Release: ${row.release_date === null ? 'Unavailable' : date(row.release_date)}<br>TMDB popularity: ${fixed(row.popularity)}`,
      });
      const container = $('recommendations');
      if (!region.recommendations.length) {
        empty('recommendations', 'No recommendations qualify for this market in the current snapshot.');
        return chart;
      }
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
      return chart;
    }
    select.addEventListener('change', update);
    return update();
  }

  async function render(bundle) {
    freshness(bundle.metadata);
    metric('total-movies', bundle.overview.total_movies);
    metric('rated-movies', bundle.overview.rated_movies);
    $('rating-coverage').textContent = bundle.overview.total_movies ? `${fixed(bundle.overview.rated_movies / bundle.overview.total_movies * 100, 1)}% of catalog titles` : 'Rating coverage unavailable';
    metric('average-rating', bundle.overview.avg_rating, '/ 10');
    metric('average-runtime', bundle.overview.avg_runtime_minutes, 'min');
    highlight('highest-rated', bundle.overview.highest_rated_movie);
    highlight('most-voted', bundle.overview.most_voted_movie);
    renderRankings(bundle);
    // Chart containers must be visible before Plotly measures them.
    $('dashboard').hidden = false;
    const filteredCharts = [renderPeople(bundle), renderMarkets(bundle)];
    for (const [key, label] of Object.entries(metricLabels)) {
      $('metric-definitions').append(element('dt', label), element('dd', bundle.metadata.metric_definitions[key]));
    }
    for (const limitation of bundle.metadata.limitations) $('limitations').append(element('li', limitation));
    await Promise.all([...renderCharts(bundle), ...filteredCharts]);
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

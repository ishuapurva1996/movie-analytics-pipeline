/* Local design comparison. Existing public contract v1. This page fetches one atomic, validated bundle. */
(() => {
  'use strict';

  const DAY = 86_400_000;
  // Charts and interface share the comparison route's palette.
  function chartPalette(node) {
    const styles = getComputedStyle(node);
    return Object.fromEntries(['ink', 'muted', 'panel', 'line', 'green', 'runtime', 'chart-context', 'count-low', 'count-mid', 'count-high', 'market-india'].map(key => [key, styles.getPropertyValue(`--${key}`).trim()]));
  }
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
  const rolePlurals = { actor: 'actors', actress: 'actresses', director: 'directors', writer: 'writers', producer: 'producers', cinematographer: 'cinematographers', composer: 'composers', editor: 'editors', production_designer: 'production designers', casting_director: 'casting directors', archive_footage: 'people in archive footage' };
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
  const mobileLayout = window.matchMedia('(max-width: 720px)');
  const chartSpecs = new Map();
  const sizeKeySpecs = new Map();
  // Wrap category labels, while preserving full source text in hover and tables.
  function categoryLabel(value) {
    const label = text(value);
    const width = mobileLayout.matches ? 18 : 30;
    if (label.length <= width) return plotText(label);
    let split = label.lastIndexOf(' ', width);
    if (split < width / 2) split = width;
    const second = label.slice(split).trim();
    return `${plotText(label.slice(0, split))}<br>${plotText(second.length > width ? `${second.slice(0, width - 1)}…` : second)}`;
  }
  const fixed = (value, digits = 2) => value == null ? 'Unavailable' : value.toFixed(digits);
  function ratingRange(rows, key, initial, padding = .1) {
    const values = rows.map(row => row[key]).filter(Number.isFinite);
    return [Math.max(0, Math.min(initial[0], ...values.map(value => Math.floor((value - padding) * 2) / 2))),
      Math.min(10, Math.max(initial[1], ...values.map(value => Math.ceil((value + padding) * 2) / 2)))];
  }
  const movieHover = row => `${plotText(row.title)}<br>Rank: ${row.rank}<br>Rating: ${fixed(row.rating)} / 10<br>Votes (IMDb first): ${number(row.votes)}`;

  function element(tag, content, className) {
    const node = document.createElement(tag);
    if (content !== undefined) node.textContent = content;
    if (className) node.className = className;
    return node;
  }

  function empty(target, message) {
    $(target).replaceChildren(element('p', message, 'empty-state'));
  }

  function table(target, caption, columns, rows, emptyMessage = 'No entries meet these rules in the latest data.') {
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
      $('freshness-notice').textContent = `Data is over eight days old: ${stale.join(' and ')}. The latest available data is shown below.`;
      $('freshness-notice').hidden = false;
    }
    $('synthetic-notice').hidden = !metadata.synthetic;
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

  function renderHighlights(overview) {
    const rated = overview.highest_rated_movie;
    const voted = overview.most_voted_movie;
    const shared = Boolean(rated?.movie_id && rated.movie_id === voted?.movie_id);
    $('movie-spotlight').dataset.sharedLeader = String(shared);
    $('spotlight-title').textContent = shared ? text(rated.title) : 'Highest rating and most votes';
    for (const [target, movie, key, unit] of [['highest-rated', rated, 'rating', '/ 10'], ['most-voted', voted, 'votes', 'votes (IMDb first)']]) {
      if (!movie) { empty(target, 'No movie meets these rules in the latest data.'); continue; }
      if (!shared) $(target).append(element('p', text(movie.title), 'spotlight-movie'));
      const value = element('p', undefined, 'highlight-value');
      value.append(element('strong', number(movie[key], key === 'rating')), document.createTextNode(` ${unit}`));
      $(target).append(value);
    }
  }

  const MAX_DOT_DIAMETER = 26;
  // The people snapshot clusters around five films. Keep these count bands
  // stable across roles; area references are independent of the color cutoffs.
  const PEOPLE_COUNT_BANDS = [{ value: 4, upper: 4 }, { value: 6, upper: 7 }, { value: 10, upper: Infinity }];
  function countSizeScale(rows, key) {
    return Math.max(0, ...rows.map(row => row[key]).filter(Number.isFinite));
  }
  function dotDiameter(value, maximum) {
    // Radius grows with sqrt(count), so visible filled-circle AREA grows with
    // count. Never scale diameter directly with the count or impose a floor.
    return Number.isFinite(value) && value > 0 && maximum > 0 ? MAX_DOT_DIAMETER * Math.sqrt(value / maximum) : 8;
  }
  function countSamples(maximum) {
    if (maximum <= 0) return [];
    const power = 10 ** Math.floor(Math.log10(maximum / 3));
    const step = Math.max(1, [1, 2, 5, 10].filter(value => value * power <= maximum / 3).at(-1) * power || power);
    const intervals = Math.max(1, Math.floor(maximum / step));
    return [...new Set([1, Math.ceil(intervals / 2), intervals].map(value => value * step))];
  }
  function countColor(value, maximum, theme, bands) {
    if (!Number.isFinite(value) || value <= 0 || maximum <= 0) return theme['chart-context'];
    // Discrete blue/green/red bands avoid blending the legend colors together.
    // Other charts use midpoints between their existing area-reference counts.
    const samples = bands ? bands.map(band => band.value) : countSamples(maximum);
    const index = samples.findIndex((sample, i) => bands ? value <= bands[i].upper : i === samples.length - 1 || value <= (sample + samples[i + 1]) / 2);
    const tokens = samples.length === 3 ? ['count-low', 'count-mid', 'count-high']
      : samples.length === 2 ? ['count-low', 'count-high'] : ['count-high'];
    return theme[tokens[index]];
  }
  function sizeKey(target, rows, key, maximum, label, bands) {
    sizeKeySpecs.set(target, { rows, key, maximum, label, bands });
    const container = $(target);
    container.replaceChildren();
    container.hidden = !rows.length;
    if (!rows.length) return;
    const theme = chartPalette(container);
    container.append(element('p', `Size & color: ${label}`, 'size-key-label'));
    if (maximum > 0) {
      const values = bands ? bands.map(band => band.value) : countSamples(maximum);
      const samples = element('div', undefined, 'size-key-samples');
      const compact = new Intl.NumberFormat('en-US', { notation: 'compact', maximumFractionDigits: 1 });
      for (const [index, value] of values.entries()) {
        const sample = element('span', undefined, 'size-key-sample');
        const swatch = element('span', undefined, 'size-key-circle');
        const diameter = dotDiameter(value, maximum);
        swatch.style.width = `${diameter}px`;
        swatch.style.height = `${diameter}px`;
        swatch.style.backgroundColor = countColor(value, maximum, theme, bands);
        swatch.dataset.count = String(value);
        swatch.setAttribute('aria-hidden', 'true');
        const lower = bands ? (index ? bands[index - 1].upper : 0) : index ? (values[index - 1] + value) / 2 : 0;
        const upper = bands ? (Number.isFinite(bands[index].upper) ? bands[index].upper : null) : index < values.length - 1 ? (value + values[index + 1]) / 2 : null;
        const band = bands ? (upper === null ? `${lower + 1}+` : `${lower + 1}–${upper}`)
          : upper === null ? (lower ? `>${compact.format(lower)}` : 'All counts')
            : lower ? `${compact.format(lower)}–${compact.format(upper)}` : `≤${compact.format(upper)}`;
        const caption = element('span', undefined, 'size-key-caption');
        caption.append(element('span', compact.format(value)), element('span', band, 'size-key-band'));
        sample.append(swatch, caption);
        sample.title = `${number(value)} ${label} (dot area reference). Color: ${lower ? `above ${number(lower)}` : 'positive counts'}${upper === null ? '' : ` up to ${number(upper)}`} ${label}.`;
        samples.append(sample);
      }
      container.append(samples);
    }
    const missing = rows.some(row => !Number.isFinite(row[key]) || row[key] <= 0);
    if (missing) container.append(element('span', 'Open dots: zero or unavailable counts', 'caption'));
  }

  function plot(target, rows, labelKey, valueKey, options = {}) {
    chartSpecs.set(target, { rows, labelKey, valueKey, options });
    const node = $(target);
    // Read inherited tokens so plots, tooltips and legends follow both themes.
    const theme = chartPalette(node);
    const { horizontal = false, rating = false, unit = 'movies', color = theme[options.colorToken] || theme.green, kind = 'bar', range, hover, idKey, focusMaximum = false, focusKey = valueKey, sizeKey: sizeField, sizeMaximum, digits = rating ? 2 : 0 } = options;
    const available = rows.filter(row => Number.isFinite(row[valueKey]));
    function fallback(message) {
      if (window.Plotly && node.data) window.Plotly.purge(node);
      node.replaceChildren();
      node.style.height = '';
      node.classList.add('chart-empty');
      node.textContent = message;
    }
    if (!available.length) return fallback('No values to plot. See the data below for unavailable values.');
    if (!window.Plotly) return fallback('The chart library could not load. All values are available in the data below.');
    node.classList.remove('chart-empty');
    // Keep explicit nulls in decade traces: a missing decade is a gap, never zero.
    const plotted = kind === 'line' || target === 'decade-counts-chart' ? rows : available;
    const categories = plotted.map((row, index) => kind === 'line' || target === 'decade-counts-chart' ? parseInt(row[labelKey], 10) : index);
    const values = plotted.map(row => row[valueKey]);
    const maximum = Math.max(...plotted.map(row => row[focusKey]).filter(Number.isFinite));
    const markColor = sizeField ? plotted.map(row => countColor(row[sizeField], sizeMaximum, theme, options.countBands))
      : focusMaximum ? plotted.map(row => row[focusKey] === maximum ? color : theme['chart-context']) : color;
    const labels = plotted.map(row => plotText(row[labelKey]));
    const tickLabels = plotted.map(row => horizontal ? categoryLabel(row[labelKey]) : plotText(row[labelKey]));
    const trace = {
      type: kind === 'bar' ? 'bar' : 'scatter',
      ...(kind === 'bar' ? { orientation: horizontal ? 'h' : 'v' } : { mode: kind === 'line' ? 'lines+markers' : 'markers+text', connectgaps: false, line: { color, width: 2, shape: 'linear' } }),
      x: horizontal ? values : categories, y: horizontal ? categories : values,
      ...(idKey ? { ids: plotted.map(row => String(row[idKey])) } : {}),
      marker: { color: markColor, opacity: 1, size: sizeField ? plotted.map(row => dotDiameter(row[sizeField], sizeMaximum)) : 10,
        ...(sizeField ? { sizemode: 'diameter', symbol: plotted.map(row => Number.isFinite(row[sizeField]) && row[sizeField] > 0 ? 'circle' : 'circle-open') } : {}),
        line: { width: sizeField ? plotted.map(row => Number.isFinite(row[sizeField]) && row[sizeField] > 0 ? 0 : 1) : 0, color: sizeField ? markColor : color } },
      ...(horizontal ? { text: values.map(value => fixed(value, digits)), textposition: kind === 'dot' ? 'middle right' : 'outside', cliponaxis: false } : {}),
      customdata: plotted.map((row, index) => hover ? hover(row) : `${labels[index]}<br>${fixed(row[valueKey], digits)} ${unit}`),
      hovertemplate: '%{customdata}<extra></extra>',
    };
    const wideScreen = window.innerWidth >= 1800;
    const labelSize = mobileLayout.matches ? 12 : wideScreen ? 18 : 16;
    const valueSize = mobileLayout.matches ? 13 : wideScreen ? 18 : 16;
    // Separate category labels, numeric ticks and axis titles at the plot corner.
    // Automatic margins alone reserve room for text but do not create this gap.
    const categoryGutter = horizontal ? (mobileLayout.matches ? 24 : 64) : 16;
    const categorical = { tickvals: categories, ticktext: tickLabels, fixedrange: true, showgrid: false, zeroline: false, ticklabelstandoff: categoryGutter, tickfont: { size: labelSize, color: theme.ink }, automargin: true };
    const numerical = { fixedrange: true, gridcolor: theme.line, zeroline: false, rangemode: 'tozero', nticks: mobileLayout.matches ? 5 : 6, ticklabelstandoff: horizontal ? 16 : (mobileLayout.matches ? 40 : 64), title: { text: unit, font: { size: valueSize, color: theme.muted }, standoff: 24 }, ...(range ? { range } : rating ? { range: [0, 10] } : {}), automargin: true };
    if (!rating && !digits) numerical.tickformat = ',.0f';
    if (horizontal) categorical.range = [plotted.length - .15, -.5];
    if (target.startsWith('decade-')) {
      categorical.tickangle = 0;
      // At narrow widths, keep the chronology without crowding fourteen labels.
      if (node.clientWidth < 650) {
        const indexes = categories.map((_, index) => index).filter(index => index % 2 === 0 || index === categories.length - 1);
        categorical.tickvals = indexes.map(index => categories[index]);
        categorical.ticktext = indexes.map(index => tickLabels[index]);
        categorical.tickangle = -40;
      }
    }
    const rowHeight = target.startsWith('genre-') ? (mobileLayout.matches ? 36 : wideScreen ? 46 : 42) : mobileLayout.matches ? 52 : wideScreen ? 68 : 60;
    const height = horizontal ? Math.max(380, plotted.length * rowHeight + 136) : mobileLayout.matches ? 374 : wideScreen ? 584 : 524;
    node.style.height = `${height}px`;
    const layout = {
      autosize: true, height, paper_bgcolor: theme.panel, plot_bgcolor: theme.panel,
      font: { family: 'Segoe UI, Arial, sans-serif', color: theme.muted, size: valueSize },
      margin: { t: 20, b: mobileLayout.matches ? 96 : 108, l: horizontal ? (mobileLayout.matches ? 116 : wideScreen ? 280 : 250) : (mobileLayout.matches ? 54 : 80), r: horizontal ? (mobileLayout.matches ? 44 : 80) : 20 },
      bargap: target === 'histogram-chart' ? .04 : horizontal ? .32 : .24, showlegend: false,
      xaxis: horizontal ? numerical : categorical, yaxis: horizontal ? categorical : numerical,
      hoverlabel: { bgcolor: theme.ink, bordercolor: theme.ink, font: { color: theme.panel, size: 14 } },
    };
    const config = { responsive: true, displayModeBar: false, scrollZoom: false, doubleClick: false, showTips: false };
    const draw = node.data ? window.Plotly.react : window.Plotly.newPlot;
    return draw(node, [trace], layout, config).catch(() => fallback('This chart could not render. All values are available in the data below.'));
  }

  // Presentation summaries use only the current bundle; no new data or cohorts.
  function setCopy(id, value) { $(id).textContent = value; }
  function leaders(rows, key) {
    const available = rows.filter(row => Number.isFinite(row[key]));
    if (!available.length) return [];
    const maximum = Math.max(...available.map(row => row[key]));
    return available.filter(row => row[key] === maximum);
  }
  function renderTakeaways(bundle) {
    const { ratings, genres, eras } = bundle;
    const bins = leaders(ratings.bins, 'movie_count');
    if (ratings.population_count && bins.length) {
      setCopy('distribution-title', bins.length === 1 ? `${text(bins[0].bracket).replace('-', '–')} is the most common rating range` : `${bins.length} rating ranges tie for the most movies`);
    }
    const summaries = [
      ['genre-rating-title', genres.ratings, 'avg_rating', 'genre', 'has the highest average movie rating', 'genres tie for the highest average movie rating'],
      ['genre-runtime-title', genres.runtimes, 'avg_runtime_minutes', 'genre', 'Genre has the longest movies on average', 'genres tie for the longest movies on average'],
      ['decade-count-title', eras.counts, 'movie_count', 'decade', 'has the most movies in this catalog', 'decades tie for the most movies in this catalog'],
      ['decade-rating-title', eras.ratings, 'avg_rating', 'decade', 'has the highest average movie rating', 'decades tie for the highest average movie rating'],
    ];
    for (const [id, rows, key, label, singular, plural] of summaries) {
      const top = leaders(rows, key);
      if (!top.length) continue;
      const prefix = id === 'decade-count-title' ? `${text(top[0][label])}: the most movies in this catalog`
        : id === 'decade-rating-title' ? `${text(top[0][label])}: the highest average movie rating`
        : `${text(top[0][label])} ${singular}`;
      setCopy(id, top.length === 1 ? prefix : `${top.length} ${plural}`);
    }
    setCopy('movies-title', 'Top 10 films of all time');
    setCopy('years-title', 'Top 10 release years by average movie rating');
  }

  function renderCharts(bundle) {
    const histogram = bundle.ratings.population_count ? Array.from({ length: 10 }, (_, order) =>
      bundle.ratings.bins.find(bin => bin.order === order) || { bracket: `${order}-${order + 1}`, order, movie_count: 0, percentage: 0 }) : [];
    $('histogram-population').append(element('strong', number(bundle.ratings.population_count)), document.createTextNode('movies counted'));
    const chartTasks = [plot('histogram-chart', histogram, 'bracket', 'percentage', {
      unit: 'Movies counted (%)', digits: 2, focusMaximum: true, focusKey: 'movie_count',
      hover: row => `${plotText(row.bracket)}<br>Movies: ${number(row.movie_count)}<br>Share: ${fixed(row.percentage)}%<br>Movies counted: ${number(bundle.ratings.population_count)}`,
    })];
    table('histogram-table', 'Movies counted in each rating range', [
      { key: 'bracket', label: 'Rating range', rowHeader: true },
      { key: 'movie_count', label: 'Movies', className: 'numeric', format: number },
      { key: 'percentage', label: 'Share', className: 'numeric', format: value => `${number(value, true)}%` },
    ], histogram, 'No movies meet the vote rules for this chart.');
    const byMetric = (rows, key) => [...rows].sort((a, b) => (b[key] ?? -Infinity) - (a[key] ?? -Infinity) || a.genre.localeCompare(b.genre));
    const decades = (rows, key) => rows.length ? Array.from({ length: 14 }, (_, index) => {
      const decade = `${1890 + index * 10}s`;
      return rows.find(row => row.decade === decade) || { decade, [key]: null };
    }) : [];
    for (const definition of [
      { id: 'genre-ratings', rows: byMetric(bundle.genres.ratings, 'avg_rating'), label: 'genre', value: 'avg_rating', heading: 'Genre', metric: 'Average rating / 10', rating: true, unit: 'Average movie rating (/10)', horizontal: true, focusMaximum: true },
      { id: 'genre-runtimes', rows: byMetric(bundle.genres.runtimes, 'avg_runtime_minutes'), label: 'genre', value: 'avg_runtime_minutes', heading: 'Genre', metric: 'Average length (min)', unit: 'Average movie length (min)', digits: 1, horizontal: true, colorToken: 'runtime', focusMaximum: true },
      { id: 'decade-counts', rows: decades(bundle.eras.counts, 'movie_count'), label: 'decade', value: 'movie_count', heading: 'Decade', metric: 'Movies counted', unit: 'Movies in catalog', focusMaximum: true, hover: row => `${plotText(row.decade)}<br>Movies: ${number(row.movie_count)}${row.decade === '2020s' ? '<br>Incomplete decade' : ''}` },
      { id: 'decade-ratings', rows: decades(bundle.eras.ratings, 'avg_rating'), label: 'decade', value: 'avg_rating', heading: 'Decade', metric: 'Average rating / 10', kind: 'line', rating: true, range: ratingRange(bundle.eras.ratings, 'avg_rating', [10, 0], .5), unit: 'Average movie rating (/10)', colorToken: 'runtime', hover: row => `${plotText(row.decade)}<br>Average rating: ${fixed(row.avg_rating)} / 10${row.decade === '2020s' ? '<br>Incomplete decade' : ''}` },
    ]) {
      chartTasks.push(plot(`${definition.id}-chart`, definition.rows, definition.label, definition.value, definition));
      table(`${definition.id}-table`, definition.metric, [
        { key: definition.label, label: definition.heading, rowHeader: true },
        { key: definition.value, label: definition.metric, className: 'numeric', format: value => definition.value === 'movie_count' ? number(value) : fixed(value, definition.value === 'avg_runtime_minutes' ? 1 : 2) },
      ], definition.rows);
    }
    const movieSizeMaximum = countSizeScale(bundle.top_movies, 'votes');
    const yearSizeMaximum = countSizeScale(bundle.eras.top_years, 'movie_count');
    sizeKey('top-movies-size-key', bundle.top_movies, 'votes', movieSizeMaximum, 'votes (IMDb first)');
    sizeKey('top-years-size-key', bundle.eras.top_years, 'movie_count', yearSizeMaximum, 'films counted');
    chartTasks.push(plot('top-movies-chart', bundle.top_movies, 'title', 'rating', {
      horizontal: true, rating: true, kind: 'dot', range: ratingRange(bundle.top_movies, 'rating', [8, 10]), unit: 'Movie rating (/10)', hover: movieHover, idKey: 'movie_id',
      sizeKey: 'votes', sizeMaximum: movieSizeMaximum,
    }));
    chartTasks.push(plot('top-years-chart', bundle.eras.top_years, 'year', 'avg_rating', {
      horizontal: true, rating: true, kind: 'dot', range: ratingRange(bundle.eras.top_years, 'avg_rating', [6.5, 7]), unit: 'Average movie rating (/10)',
      sizeKey: 'movie_count', sizeMaximum: yearSizeMaximum,
      hover: row => `${row.year}<br>Rank: ${row.rank}<br>Average rating: ${fixed(row.avg_rating)} / 10<br>Films counted: ${number(row.movie_count)}`,
    }));
    return chartTasks;
  }

  function renderRankings(bundle) {
    table('top-movies-table', 'Top movies · 100,000+ votes on either source', [
      { key: 'rank', label: 'Rank', className: 'rank-cell', format: number },
      { key: 'title', label: 'Movie', className: 'title-cell', rowHeader: true },
      { key: 'rating', label: 'Rating / 10', className: 'numeric', format: value => fixed(value) },
      { key: 'votes', label: 'Votes (IMDb first)', className: 'numeric', format: number },
    ], bundle.top_movies, 'No movies meet the vote rules for this ranking.');
    table('top-years-table', 'Top release years · 5+ films meeting the vote rules per year', [
      { key: 'rank', label: 'Rank', className: 'rank-cell', format: number },
      { key: 'year', label: 'Release year', rowHeader: true },
      { key: 'avg_rating', label: 'Average rating / 10', className: 'numeric', format: value => fixed(value) },
      { key: 'movie_count', label: 'Films counted', className: 'numeric', format: number },
    ], bundle.eras.top_years, 'No release years meet the rules for this ranking.');
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
    // Keep one count-to-area scale across ALL role selections, like the rating axis.
    const sizeMaximum = countSizeScale(bundle.people, 'movie_count');
    function update() {
      const [, label, minimum] = roles.find(role => role[0] === select.value);
      $('people-threshold').textContent = `${minimum}+ films meeting the vote rules per person`;
      const people = bundle.people.filter(person => person.role === select.value);
      $('people-chart-title').textContent = `Top 10 ${rolePlurals[select.value]}`;
      sizeKey('people-size-key', people, 'movie_count', sizeMaximum, 'films counted', PEOPLE_COUNT_BANDS);
      const chart = plot('people-chart', people.filter(person => person.rank <= 10), 'name', 'avg_rating', {
        horizontal: true, rating: true, kind: 'dot', range, unit: 'Average movie rating (/10)', idKey: 'person_id',
        sizeKey: 'movie_count', sizeMaximum, countBands: PEOPLE_COUNT_BANDS,
        hover: row => `${plotText(row.name)}<br>Role: ${plotText(label)}<br>Rank: ${row.rank}<br>Average movie rating: ${fixed(row.avg_rating)} / 10<br>Films counted: ${number(row.movie_count)}`,
      });
      table('people-table', `${label} · up to 20 people`, [
        { key: 'rank', label: 'Rank', className: 'rank-cell', format: number },
        { key: 'name', label: 'Name', className: 'title-cell', rowHeader: true },
        { key: 'movie_count', label: 'Films counted', className: 'numeric', format: number },
        { key: 'avg_rating', label: 'Average rating / 10', className: 'numeric', format: value => fixed(value) },
      ], people, 'No people meet the rules for this role in the latest data.');
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
      count.append(element('span', `${markets[market]} · movies`), element('strong', number(bundle.now_playing.regions[market].movie_count)));
      counts.append(count);
    }
    function update() {
      const market = select.value;
      const region = bundle.now_playing.regions[market];
      for (const node of counts.children) node.classList.toggle('is-selected', node.dataset.market === market);
      $('market-snapshot').textContent = `${markets[market]} · data collected ${date(bundle.metadata.tmdb_capture_dates[market])}`;
      $('now-playing-chart-title').textContent = `Top 5 movies in ${market === 'US' ? 'the United States' : 'India'}`;
      const chart = plot('now-playing-chart', region.recommendations, 'title', 'rating', {
        horizontal: true, rating: true, unit: 'Movie rating (/10)', idKey: 'movie_id',
        colorToken: market === 'IN' ? 'market-india' : 'green',
        hover: row => `${movieHover(row)}<br>Country: ${markets[market]}<br>Release date: ${row.release_date === null ? 'Unavailable' : date(row.release_date)}<br>TMDB popularity: ${fixed(row.popularity)}`,
      });
      const container = $('recommendations');
      if (!region.recommendations.length) {
        empty('recommendations', 'No movies meet the recommendation rules for this country in the latest data.');
        return chart;
      }
      const list = element('ol', undefined, 'recommendation-list');
      for (const movie of region.recommendations) {
        const item = element('li', undefined, 'recommendation');
        const rank = element('span', String(movie.rank).padStart(2, '0'), 'recommendation-rank');
        rank.setAttribute('aria-label', `Rank ${movie.rank}`);
        const content = element('div');
        content.append(element('h4', text(movie.title)));
        content.append(element('p', `Rating: ${number(movie.rating, true)}${movie.rating === null ? '' : ' / 10'} · Votes (IMDb first): ${number(movie.votes)} · TMDB popularity: ${number(movie.popularity, true)} · Release: ${movie.release_date === null ? 'Unavailable' : date(movie.release_date)}`, 'recommendation-meta'));
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
    renderHighlights(bundle.overview);
    renderTakeaways(bundle);
    renderRankings(bundle);
    // Chart containers must be visible before Plotly measures them.
    $('dashboard').hidden = false;
    const filteredCharts = [renderPeople(bundle), renderMarkets(bundle)];
    for (const [key, label] of Object.entries(metricLabels)) {
      $('metric-definitions').append(element('dt', label), element('dd', bundle.metadata.metric_definitions[key]));
    }
    for (const limitation of bundle.metadata.limitations) $('limitations').append(element('li', limitation));
    await Promise.all([...renderCharts(bundle), ...filteredCharts]);
    updateNavigation();
    $('load-status').textContent = 'Movie data loaded. Update dates are in About the data.';
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
        : 'Movie data could not be loaded. Please try reloading later. No sample data is shown.';
    }
  }
  // Recompose category labels at the mobile breakpoint without refetching data.
  mobileLayout.addEventListener('change', () => {
    for (const [target, spec] of chartSpecs) plot(target, spec.rows, spec.labelKey, spec.valueKey, spec.options);
  });
  document.addEventListener('dashboard-theme-change', () => {
    for (const [target, spec] of sizeKeySpecs) sizeKey(target, spec.rows, spec.key, spec.maximum, spec.label, spec.bands);
    for (const [target, spec] of chartSpecs) plot(target, spec.rows, spec.labelKey, spec.valueKey, spec.options);
  });
  const sectionLinks = [...document.querySelectorAll('.section-nav a')];
  let scheduled = false;
  function updateNavigation() {
      scheduled = false;
      if ($('dashboard').hidden) return;
      const boundary = document.querySelector('.section-nav').getBoundingClientRect().bottom + 140;
      const active = sectionLinks.filter(link => $(link.hash.slice(1)).getBoundingClientRect().top <= boundary).at(-1) || sectionLinks[0];
      for (const link of sectionLinks) {
        if (link === active) link.setAttribute('aria-current', 'location');
        else link.removeAttribute('aria-current');
      }
  }
  window.addEventListener('scroll', () => {
    if (!scheduled) { scheduled = true; requestAnimationFrame(updateNavigation); }
  }, { passive: true });
  load();
})();

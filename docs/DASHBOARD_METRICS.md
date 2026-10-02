# Dashboard metrics and public data contract

The dashboard describes the current replacement build of this project's movie warehouse. It does not retain historical now-playing snapshots. The public bundle is a bounded selection of aggregate metrics and ranked rows, defined by [`data-contract.schema.json`](../web_dashboard/data-contract.schema.json). Real exports are generated artifacts; [`synthetic-dashboard.json`](../tests/fixtures/dashboard/synthetic-dashboard.json) is visibly invented test data and must never be a production fallback.

## Population and source preference

The catalog comes from `CURATED.DIM_MOVIES`: IMDb `movie` and `tvMovie` records with no end year, plus titles from the current TMDB enrichment. Adult content is not excluded. TMDB enrichment covers distinct IDs in the current United States/India now-playing extract, not the complete TMDB catalog. A title is not evidence of a production country, language, or industry classification.

Most rating models use `COALESCE(imdb_avg_rating, tmdb_avg_rating)` and independently use `COALESCE(imdb_num_of_votes, tmdb_num_of_votes)`. `COALESCE` chooses the first non-null value. Thus the displayed rating and vote count can come from different sources. An eligibility condition can admit a film because of TMDB votes even when the displayed count is the smaller IMDb count. Say “100,000+ votes on either source; IMDb rating preferred,” not “100,000 IMDb votes.” Unknown values stay JSON `null` and display as unavailable, never as zero.

## Metric mapping

All source names below are existing `ANALYTICS` relations unless prefixed with `CURATED`. The production exporter uses explicit column allowlists.

| Public field | Source columns | Population and interpretation |
| --- | --- | --- |
| `overview.total_movies` | `total_movies.total_movies` | Distinct catalog movie IDs in `CURATED.DIM_MOVIES`. |
| `overview.rated_movies` | `rated_movies.total_rated_movies` | Distinct movie IDs with a non-null IMDb or TMDB rating. No vote threshold. |
| `overview.avg_rating` | `avg_movie_rating.avg_movie_rating` | Unweighted mean of the preferred rating over rated rows, rounded to two decimals by the model. A film with many votes has the same weight as another film. |
| `overview.avg_runtime_minutes` | `average_runtime.average_runtime` | Mean runtime over catalog rows with runtime between 40 and 300 minutes inclusive. Unknown/out-of-range runtimes are excluded. |
| `overview.highest_rated_movie` | `highest_rated_movie.movie_id`, `movie_name`, `avg_rating`, `num_of_votes` | At least 100,000 votes on either source and a known rating. Sort rating descending, preferred votes descending, movie ID ascending. |
| `overview.most_voted_movie` | `most_popular_movie.movie_id`, `movie_name`, `avg_rating`, `num_of_votes` | Known preferred rating and vote count. Sort preferred votes descending, movie ID ascending. UI label: **Most voted movie**; this is not TMDB popularity. |
| `ratings.bins`, `population_count` | `mart_rating_distribution.rating_bracket`, `bucket_order`, `movie_count`, `percentage_of_movies`, `total_no_of_movies` | Known rating; IMDb at least 1,000 votes **or** TMDB at least 500. Denominator is this qualifying population, not all rated titles. Lower edge inclusive, upper edge exclusive, except 9–10 includes exactly 10. Empty bins may be absent. |
| `genres.ratings` | `average_rating_by_genre.genre_name`, `genre_avg_rating` | At least 1,000 votes on either source. Mean of non-null preferred ratings within each genre. A movie contributes to every associated genre. |
| `genres.runtimes` | `average_runtime_by_genre.genre_name`, `genre_avg_runtime` | Genre mean runtime, restricted to 40–300 minutes. It has a different population from the genre rating chart. |
| `eras.counts` | `no_of_movies_every_decade.decade`, `movies_made_in_decade` | Catalog rows with known year in 1890–2029 and runtime 40–300 minutes. These are qualifying catalog counts, not worldwide production totals. |
| `eras.ratings` | `decade_avg_rating.decade`, `decade_avg_rating` | Mean preferred non-null rating with the era vote floors below. No runtime restriction. Null decade rows, representing years outside the displayed 1890–2029 range, are excluded from the public export. |
| `eras.top_years` | `mart_top_years.release_year`, `release_yr_avg_rating`, `movie_count` | Top ten years by rounded mean preferred rating, then release year ascending; at least five qualifying distinct films per year. Includes source release years outside the displayed decade range when eligible. Rank is assigned in export order. A ranking, not a complete time series. |
| `top_movies` | `mart_top_movies.movie_rank`, `movie_id`, `movie_name`, `avg_rating`, `num_of_votes` | At most ten films with at least 100,000 votes on either source. Rating descending, preferred votes descending, movie ID ascending. A qualifying row with unknown rating remains null. |
| `people` | `mart_top_people.job_role`, `job_rank`, `person_id`, `person_name`, `movie_count`, `person_rating` | At most 20 people per supported role, qualifying films with at least 100,000 votes on either source, and the per-role minimum below. Rating descending, person ID ascending. Birth and death years are not published. |
| `now_playing.regions.*.movie_count` | `number_of_movies_now_playing.tmdb_region`, `no_of_movies_now_playing` | Current count per exhibition market; not a production-country count. The same film can appear in both markets, so their sum is not a unique film count. |
| `now_playing.regions.*.recommendations` | `mart_now_playing_recommendations.recommendation_rank`, `movie_id`, `movie_name`, `now_playing_release_date`, `now_playing_overview`, `avg_rating`, `num_of_votes`, `now_playing_popularity` | At most five per market; IMDb at least 10,000 votes **or** TMDB at least 1,000. Sort rating descending, preferred votes descending, TMDB popularity descending, movie ID ascending. Empty is valid when no film qualifies. |
| `now_playing.latest_snapshot_date` | `latest_now_playing_snapshot.latest_now_playing_snapshot` | Global maximum capture date, supplementary only; cannot establish freshness in both markets. |
| `metadata.tmdb_capture_dates` | Bounded aggregate over `CURATED.FCT_NOW_PLAYING` | Validate both US/IN, equal minimum/maximum capture date within each region, valid dates, and uniqueness of `(tmdb_id, tmdb_region)`. Public JSON includes only the two dates; private validation counts reconcile the market counts. |

Genre names are not harmonized across IMDb and TMDB vocabularies. The unused `total_genres` KPI counts a broader dimension population than the displayed movies and is deliberately excluded. Existing `top_tated_genres` is not used or renamed.

## Era vote floors

Decade ratings and top years select the preferred vote count independently of the rating: IMDb votes when known, otherwise TMDB votes. This is a selected-source threshold, unlike the either-source thresholds above.

| Release year | Minimum preferred votes |
| --- | ---: |
| Before 1900 | 20 |
| 1900–1929 | 50 |
| 1930–1949 | 100 |
| 1950–1969 | 500 |
| 1970–1989 | 1,000 |
| 1990 onward | 10,000 |

## People methodology

Ratings summarize qualifying films represented in IMDb principal credits. This is not a person's full filmography and does not measure their individual performance. The model counts distinct movie IDs for the minimum; its rating mean uses qualifying principal-credit rows. Repeated credits for the same person/film/role can therefore weight that film more than once; this dashboard preserves the model's current meaning.

| Role | Minimum qualifying movies |
| --- | ---: |
| Actor, actress, editor, archive footage, casting director | 5 |
| Production designer, producer, cinematographer, composer, writer | 4 |
| Director | 3 |

## Freshness, ordering, and validation

`metadata.warehouse_completed_at` is the successful dbt build completion time from the owning eligible Airflow run. `metadata.exported_at` is the time that run's validated bundle was exported. Both are UTC timestamps ending in `Z`. `metadata.tmdb_capture_dates.US` and `.IN` are extractor-local calendar dates, not precise timestamps or proof that the entire pipeline completed. IMDb capture time is unavailable and `metadata.imdb_capture_date` remains `null`.

The dashboard is stale when more than eight days have elapsed since warehouse completion, or more than eight calendar days have elapsed since either region's capture date. This is a grace period for the weekly Monday pipeline. Code-only redeployment must preserve all source/export timestamps. Missing/invalid capture or completion metadata fails export instead of inventing freshness.

The v1 bundle uses snake_case keys, finite numbers and JSON nulls. Rank lists sort missing numeric values last and use stable IDs for ties; years use year ascending. Unique IDs are required per list, per people role and per recommendation region. Histogram labels/order are unique and ordered; counts sum to the declared denominator. Percentages are rounded to two decimals. A tolerance of 0.051 percentage points around 100 permits the accumulated rounding of ten bins (maximum 0.05) plus numeric representation error. An empty histogram has denominator zero and no bins.

Schema validation rejects extra fields, malformed dates, unsupported versions, out-of-range ratings, negative counts and excess ranked rows. Semantic validation additionally checks uniqueness, deterministic ordering, rank continuity, regional coverage and count reconciliation. The initial uncompressed JSON ceiling is 2 MiB; oversized exports fail rather than truncate. Measure a real export before treating that ceiling as verified. The public `bundle_id` is opaque; Airflow run identifiers, private S3 keys, account/role/database names, credentials, raw datasets and private pointers never belong in the public bundle.

Region selection affects only now playing; role selection affects only people. Pre-aggregated and truncated marts cannot support accurate dashboard-wide year/genre filters. No such global filters are exposed.

## Publication permission and attribution

Provider requirements were checked on October 2, 2026. The [IMDb usage conditions](https://help.imdb.com/article/imdb/general-information/can-i-use-imdb-data-in-my-software/G5JTRESSHJBBHTGX) restrict republishing data as an online or offline movie database except for individual personal use. The non-commercial dataset label does not itself establish permission to publish this public portfolio's title/people ratings and votes. **The owner must establish permission or a suitable license for the intended public fields before the first real public deployment.** This remains a publication prerequisite; the requested dataset is not silently replaced or presented as approved. Bounded aggregates are an exposure limit, not a claim of permission.

Credit IMDb and link to its [dataset documentation](https://developer.imdb.com/non-commercial-datasets/). Do not redistribute raw IMDb datasets. [TMDB's FAQ](https://developer.themoviedb.org/docs/faq) permits non-commercial API use with attribution and requires an approved, unmodified [TMDB logo](https://www.themoviedb.org/about/logos-attribution) in an About/Credits section. It must be less prominent than the dashboard identity. Include the required notice: “This product uses the TMDB API but is not endorsed or certified by TMDB.” The TMDB credit links to [The Movie Database](https://www.themoviedb.org). A change to commercial use requires a separate terms/license review.

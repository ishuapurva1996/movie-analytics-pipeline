select
    movie_id,
    'imdb_avg_rating' as invalid_column,
    imdb_avg_rating as invalid_value
from {{ ref('fct_movie_ratings') }}
where imdb_avg_rating is not null
  and imdb_avg_rating not between 0 and 10

union all

select
    movie_id,
    'tmdb_avg_rating' as invalid_column,
    tmdb_avg_rating as invalid_value
from {{ ref('fct_movie_ratings') }}
where tmdb_avg_rating is not null
  and tmdb_avg_rating not between 0 and 10

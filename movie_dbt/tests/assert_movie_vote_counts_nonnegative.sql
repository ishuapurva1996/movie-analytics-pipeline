select
    movie_id,
    'imdb_num_of_votes' as invalid_column,
    imdb_num_of_votes as invalid_value
from {{ ref('fct_movie_ratings') }}
where imdb_num_of_votes is not null
  and imdb_num_of_votes < 0

union all

select
    movie_id,
    'tmdb_num_of_votes' as invalid_column,
    tmdb_num_of_votes as invalid_value
from {{ ref('fct_movie_ratings') }}
where tmdb_num_of_votes is not null
  and tmdb_num_of_votes < 0

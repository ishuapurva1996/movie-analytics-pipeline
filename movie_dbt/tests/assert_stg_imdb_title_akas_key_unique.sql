select
    imdb_id,
    alternate_title_order,
    count(*) as record_count
from {{ ref('stg_imdb_title_akas') }}
group by imdb_id, alternate_title_order
having count(*) > 1

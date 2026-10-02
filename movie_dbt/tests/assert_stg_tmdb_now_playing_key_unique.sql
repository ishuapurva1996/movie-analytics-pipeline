select
    tmdb_id,
    tmdb_region,
    snapshot_date,
    count(*) as record_count
from {{ ref('stg_tmdb_now_playing') }}
group by tmdb_id, tmdb_region, snapshot_date
having count(*) > 1

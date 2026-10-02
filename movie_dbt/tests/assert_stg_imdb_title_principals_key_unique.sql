select
    imdb_id,
    principal_order,
    count(*) as record_count
from {{ ref('stg_imdb_title_principals') }}
group by imdb_id, principal_order
having count(*) > 1

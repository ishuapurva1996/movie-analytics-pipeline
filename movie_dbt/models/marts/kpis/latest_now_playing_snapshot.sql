SELECT 
MAX(SNAPSHOT_DATE) AS Latest_Now_Playing_Snapshot
FROM {{ ref('fct_now_playing') }}

SELECT 
    AVG(RUNTIME_MIN) AS Average_Runtime
FROM {{ ref('dim_movies') }}
WHERE RUNTIME_MIN >= 40 AND RUNTIME_MIN <= 300

-- 08: RFM segments — terciles on recency / frequency / monetary, payers only.
-- Bucketing is done with row_number + count() OVER () instead of ntile(), because
-- ClickHouse has no ntile() — and doing it by hand keeps the result identical to the
-- DuckDB reference (same integer-division boundaries, no engine-specific ties).
WITH base AS (
    SELECT user_id,
           dateDiff('day', maxIf(event_date, event_type = 4), toDate('2025-12-27')) AS recency_days,
           countIf(event_type = 4) AS frequency,
           sumIf(amount, event_type = 4) AS monetary
    FROM events
    GROUP BY user_id
    HAVING frequency > 0
),
ranked AS (
    SELECT *,
           -- user_id is the tie-breaker: recency_days/frequency are integers with huge
           -- tie groups, so without it the tercile boundaries would be arbitrary.
           row_number() OVER (ORDER BY recency_days, user_id) AS r_rank,
           row_number() OVER (ORDER BY frequency DESC, monetary DESC, user_id) AS f_rank,
           row_number() OVER (ORDER BY monetary DESC, user_id) AS m_rank,
           count() OVER () AS total
    FROM base
)
SELECT if(r_rank * 3 <= total, 'recent', if(r_rank * 3 <= 2 * total, 'mid', 'stale')) AS recency_b,
       if(f_rank * 3 <= total, 'high', if(f_rank * 3 <= 2 * total, 'mid', 'low')) AS frequency_b,
       if(m_rank * 3 <= total, 'high', if(m_rank * 3 <= 2 * total, 'mid', 'low')) AS monetary_b,
       count() AS users,
       round(avg(monetary), 2) AS avg_monetary
FROM ranked
GROUP BY recency_b, frequency_b, monetary_b
ORDER BY recency_b, frequency_b, monetary_b;
-- 09: exact vs approximate cardinality — the ClickHouse cost/accuracy dial.
-- uniq() = HyperLogLog (bounded memory, ~0.5% error), uniqCombined() = HLL + exact
-- set for small cardinalities, uniqExact() = full set (memory scales with cardinality).
-- Interview angle: "how many DAU" at 50M events — uniqExact costs memory proportional
-- to the answer; uniq stays flat. This case prints the actual error for this dataset.
SELECT
    uniqExact(user_id)                                   AS exact_users,
    uniq(user_id)                                        AS hll_users,
    uniqCombined(12)(user_id)                            AS uniq_combined_users,
    round(abs(uniq(user_id) - uniqExact(user_id)) / uniqExact(user_id) * 100, 4) AS hll_err_pct
FROM events;
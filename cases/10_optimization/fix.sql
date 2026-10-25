-- Case 10 FIX: schema-side changes. Levers were tried in this order and measured
-- (numbers in README.md); only the projection moved the needle by >10x.
--
-- 1) PREWHERE (where the filter is applied)      — no help: ClickHouse already
--    moves simple filters to PREWHERE automatically here.
-- 2) skip index bloom_filter on product_id       — no help: insertion order is random
--    w.r.t. product_id, so every 8192-row granule contains product 42 and the index
--    matches every granule. Skip indexes only pay off on correlated/clustered data.
-- 3) projection ordered by product_id            — the win. Data is physically
--    re-sorted once, then the filter is a key range read.

-- (3) the projection that made the report fast
ALTER TABLE events
    ADD PROJECTION IF NOT EXISTS p_product
    (SELECT user_id, event_date, event_ts, event_type, product_id, channel, amount
     ORDER BY product_id);

-- one-off backfill of existing parts (a new INSERT would materialize it automatically)
ALTER TABLE events MATERIALIZE PROJECTION p_product;

-- verify the planner picks it up: EXPLAIN SELECT ... should mention p_product
-- EXPLAIN SELECT count() FROM events WHERE product_id = 42;

-- Revert: ALTER TABLE events DROP PROJECTION p_product;
# clickhouse-analytics

> Ten ClickHouse case studies on a 50M-row dataset, plus a projection fix that made a slow query ~100× faster.

## Navigation
- 🌐 [Portfolio site](https://nikitaboyarkin.github.io)
- 🏦 [Flagship case: Volta neobank](https://github.com/NikitaBoyarkin/volta-banking)
- 🧪 Related: [gmv-drop-rca](../gmv-drop-rca/) · [sql-analytics-case-study](https://github.com/NikitaBoyarkin/sql-analytics-case-study) · [interview-gym](../interview-gym/)

**On this page:** [Situation](#situation) · [Task](#task) · [Actions](#actions) · [Result](#result) · [Metric decomposition](#metric-decomposition) · [Quick start](#quick-start)

## Situation
ClickHouse case-study lab: 10 cases migrated from the DuckDB cookbook + one query
optimization case (`slow.sql` → `fast.sql`, EXPLAIN before/after, benchmark).

## Task
Run ten cookbook cases on ClickHouse 24.x against a seeded 50,000,000-row dataset,
and turn one slow query into a fast one — proving the win with EXPLAIN and a benchmark.

## Actions
- Migrated 10 cases from the DuckDB cookbook to ClickHouse 24.x.
- Built the optimization pair `slow.sql` → `fast.sql` with EXPLAIN before/after.
- Benchmarked p50/p95 over 100 runs and asserted `speedup >= 10`.
- Applied the schema-side fix `ADD PROJECTION … ORDER BY product_id`.

## Result
- Seeded dataset: the test asserts 50,000,000 rows.
- Funnel case rows: `[1,282176],[2,696745],[3,20730],[4,349]` (cases/expected.json).
- Sessionization: `[49711224,1000000,1.01,0.09,0.0]`.
- Optimized query: `speedup >= 10` (≥×10 target); the projection fix delivered a ~100× win.

**Status:** PRD approved, in development — see [PRD.md](PRD.md).

## Metric decomposition

`avg(amount)` over all events (45.46) is not the transaction level — it is two
independent factors multiplied: **purchase share × paid AOV**. Report them
separately:

| Factor | Value | Reading |
|---|---|---|
| Purchase share | **0.1800** (9,001,288 / 50,000,000) | how often an event is a purchase |
| Paid AOV | **252.54** | mean order value on purchases (uniform 5–500) |
| `avg(amount)` = share × AOV | 0.1800 × 252.54 = **45.46** | the decomposition is exact |

`amount` is structurally zero-inflated: 82.0% of rows are `amount = 0`, and
`amount > 0` ⟺ `event_type = 4` (9,001,288 non-zero = exactly the purchase
count). So a raw `avg(amount)` across all events is misleading — `avg(amount)`
rising without paid AOV rising just means a higher purchase share. Use
`sum(amount)` or `avg(amount) FILTER (WHERE event_type = 4)`:

```sql
SELECT count(*) FILTER (WHERE event_type = 4) * 1.0 / count(*) AS purchase_share,
       avg(amount) FILTER (WHERE event_type = 4) AS paid_aov
FROM read_parquet('data/seed.parquet');
```

Full analysis: [`reports/eda/eda-clickhouse-2026-10-13.md`](reports/eda/eda-clickhouse-2026-10-13.md).

## Quick start

```bash
docker compose up -d   # single-node ClickHouse
uv sync
uv run python scripts/run.py
```

<!-- ascii-art: pyfiglet + ascii-bin (CC0) -->
```text
    _ _    _   _                                        _      _   _
 __| (_)__| |_| |_  ___ _  _ ___ ___ ___ __ _ _ _  __ _| |_  _| |_(_)__ ___
/ _| | / _| / / ' \/ _ \ || (_-</ -_)___/ _` | ' \/ _` | | || |  _| / _(_-<
\__|_|_\__|_\_\_||_\___/\_,_/__/\___|   \__,_|_||_\__,_|_|\_, |\__|_\__/__/
                                                          |__/

╭──────────────────────────────────────────────────────────────────────────╮
│ ClickHouse case-study lab: nine cookbook cases migrated from DuckDB +... │
╰──────────────────────────────────────────────────────────────────────────╯
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

# clickhouse-analytics

> Ten ClickHouse case studies on a 50M-row dataset, plus a projection that turns a full-partition scan into a key range read.

## Navigation
- 🌐 [Portfolio site](https://nikitaboyarkin.github.io)
- 🏦 [Flagship case: Volta neobank](https://github.com/NikitaBoyarkin/volta-banking)
- 🧪 Related: [GMV drop RCA](https://nikitaboyarkin.github.io/projects/gmv-drop-rca/) · [sql-analytics-case-study](https://github.com/NikitaBoyarkin/sql-analytics-case-study)

**On this page:** [Situation](#situation) · [Task](#task) · [Actions](#actions) · [Result](#result) · [Metric decomposition](#metric-decomposition) · [Quick start](#quick-start)

## Situation
ClickHouse case-study lab: nine cookbook cases migrated from DuckDB + one query
optimization case (`slow.sql` → `fast.sql`, EXPLAIN before/after, benchmark).

## Task
Run the nine cookbook cases plus the optimization case on ClickHouse 24.x against a
seeded 50,000,000-row dataset, and turn one slow query into a fast one — the speedup
is measured by the test suite.

## Actions
- Migrated the cookbook cases to ClickHouse 24.x; seven keep a DuckDB twin as a cross-engine check.
- Built the optimization pair `slow.sql` → `fast.sql`, where the only lever is a schema-side projection.
- Timed the same query text before and after the projection (median of 3 and 5 runs) and asserted `speedup >= 10` in `tests/test_cases.py`.
- Applied the schema-side fix `ADD PROJECTION … ORDER BY product_id`.

## Result
- Seeded dataset: the test asserts 50,000,000 rows.
- Funnel case rows: `[1,282176],[2,696745],[3,20730],[4,349]` (cases/expected.json).
- Sessionization: `[49711224,1000000,1.01,0.09,0.0]`.
- Optimized query: `speedup >= 10` asserted by the test suite. The win is schema-side — the query text is identical before and after.

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
docker compose up -d            # single-node ClickHouse
uv sync --all-groups            # pytest, ruff and matplotlib live in the dev group
uv run python scripts/seed.py   # loads data/seed.parquet into ClickHouse
uv run python scripts/run.py    # nine cases vs expected.json + the DuckDB twins
uv run pytest -m integration    # snapshots, cross-engine check, >=10x speedup
```

`data/` is gitignored (the parquet is 601 MB), so `scripts/seed.py` generates it when
absent — with a different generator than the pinned artifact, see `seed.py`'s notes.
A plain `uv run pytest` runs the static suite only (56 tests, no server needed); the
three integration tests skip themselves when port 8123 is closed, which is why CI
cannot verify the snapshots or the speedup.

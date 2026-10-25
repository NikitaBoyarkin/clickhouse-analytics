# ClickHouse Case Studies — Questions & Answers

Reference notes for each case in `cases/`. All numbers come from the deterministic
50,000,000-row seed (`scripts/seed.py`, no RNG seed needed — the generator is
fully deterministic), and every row-set below is pinned two ways:
`cases/expected.json` is the ClickHouse snapshot, `tests/test_static.py` checks the
snapshot and the case set agree, `tests/test_cases.py` re-runs the same cases against
a live server.

> **What this dataset is.** A benchmark fixture, not a business dataset. The
> generator is uniform, so channels and products carry no signal: channel AOV spans
> 252.39–252.68 (0.1% spread), per-product revenue max/min is 1.08, and every
> correlation with `amount` is |r| < 0.01 except the mechanical
> `event_type ~ amount`. The value of the project is the ClickHouse idiom per case,
> not a product finding. Full profile: `reports/eda/eda-clickhouse-2026-10-13.md`.

## Dataset in one table

| Property | Value |
|---|---|
| Rows | 50,000,000 |
| Columns | `user_id` u32, `event_ts` timestamp, `event_type` u8, `product_id` u16, `channel` u8, `amount` f32 |
| Users / products | 1,000,000 / 1,000 (both dense) |
| Period | 2025-07-01 → 2025-12-27 (180 continuous days) |
| Grain | one row = one event |
| `amount` | 82.0% zeros; `amount > 0` ⟺ `event_type = 4` (purchase); paid AOV 252.54 |
| Total revenue | $2,273,202,871.50 |

---

## 01 · 1-day conversion funnel

**Q:** For a 24-hour sliding window, how many users reach each funnel step, and how
does conversion decay step to step?

**A:** 1,000,000 users reach visit, 717,824 reach cart (71.78%), 21,079 reach
checkout (2.11% of visits), 349 purchase (0.035%). Step-to-step: visit→cart 71.8%,
cart→checkout 2.94%, checkout→purchase 1.66%.

**Idiom:** `windowFunnel(86400)(event_ts, …)` — one aggregate, one pass, per user.
DuckDB needs a self-join or a recursive CTE to express the same semantics.

**Signal:** the collapse is not a product barrier. ~1.15 events per user per day
means a 24-hour window almost never contains four ordered steps. Read this case as
the `windowFunnel` idiom, and read the numbers as a property of the generator.

## 02 · Weekly retention matrix

**Q:** For each signup-week cohort, what share of users is active again in week
offset 0…4, and does retention decay?

**A:** Cohort sizes 162,159 / 23,292 / 3,244 / 476 / 63 / 9 across the six bounded
weeks. Week-1 retention 85.7%, 85.4%, 84.6%, 86.1%, 88.9%, 88.9%; week-4 retention
85.8% for the largest cohort. The curve is flat, not decaying.

**Idiom:** `toStartOfWeek(date, 1)` for Monday-start weeks plus a self-join on
`week_no`. The SQL bounds the cohort range explicitly because cohorts near the end of
the data window cannot reach week 4 — truncation, not churn.

**Signal:** flat ~85% retention is a fingerprint of uniform generation, not a
retention story. The transferable skill is the cohort-range truncation caveat.

## 03 · Sessionization

**Q:** Define a session as a run of events with no gap longer than 30 minutes. How
many sessions are there, how long are they, and how many events does one contain?

**A:** 49,711,224 sessions over 1,000,000 users — 49.7 sessions per user, 1.01 events
per session, mean duration 0.09 min, p95 duration 0.0 min.

**Idiom:** `lagInFrame(... ORDER BY event_ts)` compared against 1800 s, then a
running `sum()` over the ordered partition to number sessions. The DuckDB twin uses
plain `lag()`.

**Signal:** sessions ≈ events here. At ~1.15 events per user per day the 30-minute
rule almost never merges two rows, so a "session" is a single event. That is the
correct reading — a genuine multi-event session pattern would be visible as
`avg_events_per_session` well above 1.

## 04 · Gaps and islands

**Q:** What are the longest consecutive-day activity streaks, and who holds them?

**A:** The longest streak is 13 days (user 150,197, starting 2025-09-04), followed by
several 12-day streaks and a run of 11-day streaks that fills the top 10.

**Idiom:** `event_date - row_number() OVER (PARTITION BY user_id ORDER BY event_date)`
is constant inside a streak, so it identifies the island with no recursive CTE and no
`INTERVAL` arithmetic — in ClickHouse `Date - UInt` is a date shift.

**Signal:** streaks are the only case where the uniform generator produces
non-trivial structure (long daily runs by chance), which makes it a good test bed for
the island trick.

## 05 · Top-N products per day

**Q:** Which 3 products earn the most revenue each day, and how many rows does that
produce?

**A:** 540 rows — 180 days × 3 products. Daily top-3 revenue ranges roughly
$17.8k–$22.4k, with no product dominating: the top slot is a different product almost
every day.

**Idiom:** `LIMIT 3 BY event_date` — per-group top-N with no window function, bounded
heaps per group instead of a full sort. The DuckDB twin needs
`ROW_NUMBER() … QUALIFY`.

**Signal:** the rotation of the top slot is the uniformity showing through again. The
interview-relevant point is that `LIMIT BY` is cheaper than a window, and reviewers
notice when it is missing.

## 06 · LTV-30 by cohort

**Q:** What is average 30-day revenue per user by signup cohort — including users who
never purchased — and how many users are payers?

**A:** LTV-30 per user is 418.81 / 417.88 / 421.21 / 417.51 / 435.43 / 364.81 /
346.31 across cohorts, i.e. flat ~$418 with the tail cohorts noisy because they are
tiny. Payer share in the first 30 days is **81.3%** (659,112 of 810,757 in the
largest cohort); AOV-30 among payers is **$515.17**.

**Idiom:** `LEFT JOIN` onto per-user spend with `join_use_nulls = 1`, then
`avg(coalesce(spend, 0))`. The zero-spender denominator is the whole point: averaging
only over payers is the classic LTV overstatement.

**Signal:** LTV per user is stable and cohort-independent, as expected from a uniform
generator. The real lesson is the ClickHouse gotcha the SQL header warns about —
without `join_use_nulls = 1` a `LEFT JOIN` fills unmatched rows with type defaults
instead of NULL, so `count(spend)` counts every user as a payer and `payer_pct`
becomes a flat 100%.

> **Known discrepancy (2026-10-25).** `cases/expected.json` for case 06 currently
> holds `payers = users`, `payer_pct = 100.0`, `aov_30d = 418.81` — the un-fixed
> behaviour. Recomputed independently on `data/seed.parquet`: 81.3% payers and
> AOV-30 = 515.17, while `ltv30_per_user = 418.81` is correct in both. The snapshot
> needs regenerating against a live lab (`docker compose up -d` then
> `uv run python scripts/run.py --snapshot`) and the cause confirmed before the
> numbers above are treated as pinned. Do not quote the snapshot's payer figures.

## 07 · First-touch vs last-touch attribution

**Q:** Split each user's revenue across channels by first touch and by last touch.
How far apart are the two models, and how many users does each channel own?

**A:** First vs last touch, by channel: $793.28M vs $795.77M (349,218 / 350,080
users), $569.18M vs $567.01M, $455.32M vs $455.78M, $227.64M vs $227.33M, $227.78M vs
$227.30M. Total is $2,273.2M either way. The two models differ by under 0.4% on every
channel.

**Idiom:** `argMin(channel, (event_ts, channel))` / `argMax(...)` — any aggregate can
be "the value at the min/max of another column", so first and last touch come out of
one pass with no self-join and no window. The tuple key is deliberately minimal: a
4-field key measured 7.3 GiB on 1M groups versus ~1 GiB here.

**Signal:** models converging is what a uniform channel assignment predicts, and it
is a useful negative result — attribution disputes need non-uniform exposure to be
interesting. The engineering point is the ordering-key cost measured in the comment.

## 08 · RFM segmentation

**Q:** Bucket payers into terciles on recency, frequency and monetary value, and
describe the resulting 27 segments.

**A:** Largest segments: `recent/high/high` 124,393 users at $3,396.74 average
monetary; `stale/low/low` 131,488 users at $1,235.05; `mid/low/low` 75,979 at
$1,324.15. Monetary rises monotonically with the monetary bucket and is stable across
recency buckets — $1.2k–1.7k / $1.7k–2.3k / $2.7k–3.4k.

**Idiom:** ClickHouse has no `ntile()`, so terciles are cut with
`row_number() + count() OVER ()` and integer division. Doing it by hand also keeps the
boundaries identical to the DuckDB reference, with no engine-specific tie handling.
Recency is measured against the fixed data end date 2025-12-27.

**Signal:** the clean monetary gradient and the flat recency effect are the generator
again — no segment is genuinely "at risk". The case is worth keeping for the
no-`ntile` workaround, which is a real ClickHouse code-review point.

## 09 · Exact vs approximate cardinality

**Q:** How many distinct users are in 50M events, and what does each cardinality
function cost in accuracy?

**A:** `uniqExact` → 1,000,000 (truth, by construction). `uniq` (HyperLogLog) →
1,001,936, error 0.1936%. `uniqCombined(12)` → 1,004,952.

**Idiom:** the cost/accuracy dial — `uniqExact` keeps a set whose memory scales with
the answer; `uniq` is bounded-memory HLL; `uniqCombined` switches between exact and
approximate by cardinality.

**Signal:** a 0.19% error on a known-true 1,000,000 is the cleanest way to show what
"approximate" means in practice, and it is the answer to "how would you count DAU at
50M events without blowing memory".

## 10 · Query optimization: the 90-second product report

**Q:** An analyst's "daily revenue for product 42" query takes seconds on 50M rows.
Make it fast, and prove the win.

**A:** The query text does not change. The lever is schema-side: a projection ordered
by `product_id` (`cases/10_optimization/fix.sql`) re-sorts the data once, after which
the `product_id = 42` filter becomes a key range read instead of a scan of every
granule across all 6 monthly partitions. `tests/test_cases.py` asserts
`speedup >= 10` using the median of 3 runs before and 5 runs after.

**Levers tried, in order** (all measured, recorded in `fix.sql`'s header):

| Lever | Result |
|---|---|
| `PREWHERE` | No help — ClickHouse already moves simple filters to `PREWHERE` here |
| `bloom_filter` skip index on `product_id` | No help — insertion order is random w.r.t. `product_id`, so every 8192-row granule contains product 42 and the index matches every granule. Skip indexes need correlated/clustered data |
| Projection `ORDER BY product_id` | The win — physical re-sort once, then a key range read |

**Signal:** this is the case that separates "knows ClickHouse" from "knows SQL". Two
of the three textbook levers do nothing, and the reason is the physical layout of the
data — which is exactly what an interviewer probes. `slow.sql` and `fast.sql` differ
only in their comment headers, on purpose: the fix is not a rewrite, so timing the
same SQL before and after `fix.sql` is the honest measurement.

> **Not yet captured.** The PRD asks for stored `EXPLAIN` before/after and a
> `clickhouse-benchmark` run with p50/p95. Neither exists: the only `EXPLAIN` mention
> is a commented hint in `fix.sql`, and the test measures a median of 3/5 runs. See
> the status table in `PRD.md`.

---

## Reproducing

```bash
docker compose up -d          # single-node ClickHouse 24.8, HTTP on 8123
uv sync
uv run python scripts/seed.py # writes data/seed.parquet (630 MB) and loads MergeTree
uv run python scripts/run.py  # runs every case, diffs against cases/expected.json
uv run pytest -q              # static suite always; the 3 lab tests need the container
```

`scripts/run.py --duck-only` runs the DuckDB twins without a server;
`--snapshot` rewrites `cases/expected.json`. The seven `.duck.sql` files (cases 02–08)
are independent-engine references: a divergence means one dialect changed meaning, not
that one engine is wrong.

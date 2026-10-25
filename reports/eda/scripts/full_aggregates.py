"""Full-table aggregates for the 50M-row clickhouse-analytics seed via DuckDB.

The seed (data/seed.parquet, 50,000,000 rows) is never loaded into pandas:
every aggregate below is streamed by DuckDB. A 500k reservoir sample is used
separately for the pandas profiler and pairwise correlations.

Run:
    /Users/nikitaboarkin/Desktop/00 ide/00 portfolio/.eda-tools/.venv/bin/python \
        reports/eda/scripts/full_aggregates.py
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "data" / "seed.parquet"
OUT = Path(__file__).resolve().parent / "aggregates.json"


def main() -> None:
    con = duckdb.connect()
    con.execute(f"CREATE VIEW events AS SELECT * FROM read_parquet('{SRC}')")

    res: dict = {}

    def q(sql: str):
        return con.execute(sql).fetchall()

    def one(sql: str):
        return con.execute(sql).fetchone()

    # --- 1. shape / grain / keys -------------------------------------------------
    res["n_rows"] = one("SELECT count(*) FROM events")[0]
    res["n_users"] = one("SELECT count(DISTINCT user_id) FROM events")[0]
    res["n_products"] = one("SELECT count(DISTINCT product_id) FROM events")[0]
    res["product_range"] = one("SELECT min(product_id), max(product_id) FROM events")
    res["user_range"] = one("SELECT min(user_id), max(user_id) FROM events")
    res["ts_range"] = one("SELECT min(event_ts), max(event_ts) FROM events")
    res["n_days"] = one("SELECT count(DISTINCT CAST(event_ts AS DATE)) FROM events")
    res["nulls"] = one(
        """SELECT sum(user_id IS NULL), sum(event_ts IS NULL), sum(event_type IS NULL),
                  sum(product_id IS NULL), sum(channel IS NULL), sum(amount IS NULL)
           FROM events"""
    )
    res["full_row_dups"] = one(
        """SELECT count(*) - count(DISTINCT (user_id, event_ts, event_type, product_id, channel, amount))
           FROM events"""
    )[0]

    # --- 2. categorical distributions -------------------------------------------
    res["event_type_dist"] = q(
        "SELECT event_type, count(*) n, round(100.0*count(*)/sum(count(*)) OVER (),2) pct "
        "FROM events GROUP BY event_type ORDER BY event_type"
    )
    res["channel_dist"] = q(
        "SELECT channel, count(*) n, round(100.0*count(*)/sum(count(*)) OVER (),2) pct "
        "FROM events GROUP BY channel ORDER BY channel"
    )
    res["events_per_user"] = q(
        """SELECT round(avg(c),2) mean, median(c) median, min(c) mn, max(c) mx,
                  quantile_cont(c,0.95) p95
           FROM (SELECT user_id, count(*) c FROM events GROUP BY user_id)"""
    )[0]

    # --- 3. amount: overall + purchase-only -------------------------------------
    res["amount_overall"] = q(
        """SELECT count(*) n, round(avg(amount),4) mean, median(amount) median,
                  round(stddev(amount),4) std, min(amount) mn, max(amount) mx,
                  round(sum(amount),2) total,
                  sum(amount = 0) zeros, sum(amount > 0) nonzeros
           FROM events"""
    )[0]
    res["amount_purchase"] = q(
        """SELECT count(*) n, round(avg(amount),4) mean, median(amount) median,
                  round(stddev(amount),4) std,
                  quantile_cont(amount,0.25) p25, quantile_cont(amount,0.75) p75,
                  quantile_cont(amount,0.95) p95, min(amount) mn, max(amount) mx,
                  round(sum(amount),2) total
           FROM events WHERE event_type = 4"""
    )[0]

    # --- 4. revenue by segment ---------------------------------------------------
    res["rev_by_channel"] = q(
        """SELECT channel,
                  count(*) FILTER (WHERE event_type=4) purchases,
                  round(sum(amount),2) revenue,
                  round(100.0*sum(amount)/sum(sum(amount)) OVER (),2) rev_share,
                  round(avg(amount) FILTER (WHERE event_type=4),3) aov
           FROM events GROUP BY channel ORDER BY revenue DESC"""
    )
    res["rev_by_event_type"] = q(
        """SELECT event_type, count(*) n, round(sum(amount),2) revenue,
                  round(avg(amount),3) mean_amount
           FROM events GROUP BY event_type ORDER BY event_type"""
    )
    # product concentration
    res["rev_product_top10"] = q(
        """SELECT product_id, round(sum(amount),2) revenue
           FROM events WHERE event_type=4 GROUP BY product_id ORDER BY revenue DESC LIMIT 10"""
    )
    res["rev_product_bottom5"] = q(
        """SELECT product_id, round(sum(amount),2) revenue
           FROM events WHERE event_type=4 GROUP BY product_id ORDER BY revenue ASC LIMIT 5"""
    )
    res["rev_product_stats"] = q(
        """SELECT round(avg(revenue),2) mean, min(revenue) mn, max(revenue) mx
           FROM (SELECT product_id, sum(amount) revenue FROM events WHERE event_type=4 GROUP BY product_id)"""
    )[0]

    # --- 5. weekly trend ---------------------------------------------------------
    res["weekly"] = q(
        """SELECT date_trunc('week', CAST(event_ts AS DATE)) wk,
                  count(*) events,
                  count(DISTINCT user_id) users,
                  count(*) FILTER (WHERE event_type=4) purchases,
                  round(sum(amount),2) revenue,
                  round(sum(amount)/count(DISTINCT user_id),4) rev_per_user
           FROM events GROUP BY wk ORDER BY wk"""
    )

    # --- 6. sessionization reproduction (30-min inactivity gap) ------------------
    res["sessionization"] = q(
        """WITH marked AS (
               SELECT user_id, event_ts,
                      CASE WHEN epoch(event_ts) -
                           lag(epoch(event_ts)) OVER (PARTITION BY user_id ORDER BY event_ts)
                           > 1800 THEN 1 ELSE 0 END AS is_new
               FROM events
           ),
           sessioned AS (
               SELECT user_id, event_ts,
                      sum(is_new) OVER (PARTITION BY user_id ORDER BY event_ts
                                        ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS sess
               FROM marked
           ),
           s AS (
               SELECT user_id, sess,
                      epoch(max(event_ts)) - epoch(min(event_ts)) AS dur_sec,
                      count(*) AS ev
               FROM sessioned GROUP BY user_id, sess
           )
           SELECT count(*) sessions, count(DISTINCT user_id) users,
                  round(avg(ev),2) avg_events, round(avg(dur_sec)/60.0,2) avg_min,
                  round(quantile_cont(dur_sec,0.95)/60.0,2) p95_min
           FROM s"""
    )

    # --- 7. funnel reproduction (windowFunnel(86400) equivalent) -----------------
    # Per user, per calendar day: greedy chain visit(1)->cart(2)->checkout(3)->purchase(4)
    # in event_ts order. Day clusters are >=3 days apart in the seed, so a 24h window
    # never spans two clusters and the chain is a longest-prefix subsequence.
    res["funnel"] = q(
        """WITH g1 AS (
               SELECT user_id, CAST(event_ts AS DATE) d, min(event_ts) t1
               FROM events WHERE event_type=1 GROUP BY 1,2
           ),
           g2 AS (
               SELECT e.user_id, CAST(e.event_ts AS DATE) d, min(e.event_ts) t2
               FROM events e JOIN g1 ON e.user_id=g1.user_id AND CAST(e.event_ts AS DATE)=g1.d
               WHERE e.event_type=2 AND e.event_ts > g1.t1 GROUP BY 1,2
           ),
           g3 AS (
               SELECT e.user_id, CAST(e.event_ts AS DATE) d, min(e.event_ts) t3
               FROM events e JOIN g2 ON e.user_id=g2.user_id AND CAST(e.event_ts AS DATE)=g2.d
               WHERE e.event_type=3 AND e.event_ts > g2.t2 GROUP BY 1,2
           ),
           g4 AS (
               SELECT e.user_id, CAST(e.event_ts AS DATE) d, min(e.event_ts) t4
               FROM events e JOIN g3 ON e.user_id=g3.user_id AND CAST(e.event_ts AS DATE)=g3.d
               WHERE e.event_type=4 AND e.event_ts > g3.t3 GROUP BY 1,2
           ),
           steps AS (
               SELECT u.user_id, max(
                   1 + CASE WHEN g2.t2 IS NOT NULL THEN 1 ELSE 0 END
                     + CASE WHEN g3.t3 IS NOT NULL THEN 1 ELSE 0 END
                     + CASE WHEN g4.t4 IS NOT NULL THEN 1 ELSE 0 END) step
               FROM (SELECT DISTINCT user_id FROM events) u
               LEFT JOIN g1 ON g1.user_id=u.user_id
               LEFT JOIN g2 ON g2.user_id=u.user_id AND g2.d=g1.d
               LEFT JOIN g3 ON g3.user_id=u.user_id AND g3.d=g1.d
               LEFT JOIN g4 ON g4.user_id=u.user_id AND g4.d=g1.d
               GROUP BY u.user_id
           )
           SELECT step, count(*) users FROM steps GROUP BY step ORDER BY step"""
    )

    # --- 8. campaign / attribution sanity (channel x purchase) -------------------
    res["channel_purchase_rate"] = q(
        """SELECT channel,
                  round(100.0*count(*) FILTER (WHERE event_type=4)/count(*),3) purchase_rate_pct
           FROM events GROUP BY channel ORDER BY channel"""
    )

    OUT.write_text(json.dumps(res, default=str, indent=2))
    print(json.dumps(res, default=str, indent=2))
    print(f"\nwrote {OUT}")


if __name__ == "__main__":
    main()

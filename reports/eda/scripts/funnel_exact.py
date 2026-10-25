"""Exact reproduction of ClickHouse `windowFunnel(86400)` on the 50M-row seed.

The snapshot `cases/expected.json` -> `01_funnel` is produced by ClickHouse's
windowFunnel over each user's events. This script re-implements the *exact*
non-strict algorithm from ClickHouse source
(src/AggregateFunctions/AggregateFunctionWindowFunnel.cpp, getEventLevelNonStrictOnce)
and runs it over the full dataset in a vectorised per-user fold (no 50M pandas load).

Window = 86400 s, conditions = event_type in {1,2,3,4}.
Events are ordered by (event_ts, event_type) to match ClickHouse's pair sort.

Run:
    /Users/nikitaboarkin/Desktop/00 ide/00 portfolio/.eda-tools/.venv/bin/python \
        reports/eda/scripts/funnel_exact.py
"""

from __future__ import annotations

import json
from pathlib import Path

import duckdb
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
SRC = ROOT / "data" / "seed.parquet"
OUT = Path(__file__).resolve().parent / "funnel_exact.json"
WINDOW = 86400
CHUNK = 250_000
N_USERS = 1_000_000


def main() -> None:
    con = duckdb.connect()
    con.execute(f"CREATE VIEW events AS SELECT * FROM read_parquet('{SRC}')")

    levels = np.zeros(N_USERS + 1, dtype=np.uint8)  # index by user_id

    lo = 1
    while lo <= N_USERS:
        hi = min(lo + CHUNK - 1, N_USERS)
        df = con.execute(
            f"""
            SELECT user_id, epoch(event_ts) AS ts, event_type AS et,
                   row_number() OVER (PARTITION BY user_id
                                      ORDER BY event_ts, event_type) AS rn
            FROM events WHERE user_id BETWEEN {lo} AND {hi}
            ORDER BY user_id, rn
            """
        ).fetchnumpy()
        uid = df["user_id"].astype(np.int64)
        ts = df["ts"].astype(np.int64)
        et = df["et"].astype(np.int64)
        rn = df["rn"].astype(np.int64)

        nu = hi - lo + 1
        L = int(rn.max())
        loc = uid - lo
        ts_mat = np.full((nu, L), np.iinfo(np.int64).min // 4, dtype=np.int64)
        et_mat = np.full((nu, L), 255, dtype=np.int64)
        ts_mat[loc, rn - 1] = ts
        et_mat[loc, rn - 1] = et

        a0 = np.zeros(nu, dtype=np.int64)
        first_event = np.zeros(nu, dtype=bool)
        f1 = np.zeros(nu, dtype=np.int64)
        has1 = np.zeros(nu, dtype=bool)
        f2 = np.zeros(nu, dtype=np.int64)
        has2 = np.zeros(nu, dtype=bool)
        lvl = np.zeros(nu, dtype=np.uint8)

        for r in range(L):
            e = et_mat[:, r]
            t = ts_mat[:, r]
            valid = e != 255
            m1 = valid & (e == 1)
            a0[m1] = t[m1]
            first_event[m1] = True
            lvl[m1] = np.maximum(lvl[m1], 1)

            m2 = valid & (e == 2) & first_event
            tm = m2 & (t <= a0 + WINDOW)
            f1[tm] = a0[tm]
            has1[tm] = True
            lvl[tm] = np.maximum(lvl[tm], 2)

            m3 = valid & (e == 3) & has1
            tm = m3 & (t <= f1 + WINDOW)
            f2[tm] = f1[tm]
            has2[tm] = True
            lvl[tm] = np.maximum(lvl[tm], 3)

            m4 = valid & (e == 4) & has2
            tm = m4 & (t <= f2 + WINDOW)
            lvl[tm] = np.maximum(lvl[tm], 4)

        levels[lo : hi + 1] = lvl
        lo = hi + 1

    dist = {int(k): int(v) for k, v in zip(*np.unique(levels[1:], return_counts=True))}
    out = {
        "window": WINDOW,
        "distribution": dist,
        "as_rows": [[k, dist[k]] for k in sorted(dist)],
    }
    OUT.write_text(json.dumps(out, indent=2))
    print(json.dumps(out, indent=2))

    expected = json.loads((ROOT / "cases" / "expected.json").read_text())["01_funnel"]
    print("\nexpected:", expected)
    print("match:", out["as_rows"] == expected)


if __name__ == "__main__":
    main()

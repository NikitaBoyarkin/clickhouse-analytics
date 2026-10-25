"""Seed: deterministic 50M-row events dataset -> data/seed.parquet -> ClickHouse MergeTree.

One wide table serves all 10 cases: user_id, event_date, event_ts, event_type
(1 visit / 2 cart / 3 checkout / 4 purchase), product_id, channel, amount
(>0 only on purchases). Base date 2025-07-01, 180 days.

numpy -> pandas -> duckdb COPY (pyarrow-free parquet) -> CH INSERT ... FROM file().
Idempotent: parquet kept, CH table dropped/recreated every run.
"""

from pathlib import Path

import clickhouse_connect
import duckdb
import numpy as np
import pandas as pd

N = 50_000_000
PARQUET = Path("data/seed.parquet")
EPOCH = int(
    np.datetime64("2025-07-01T00:00:00").astype("datetime64[s]").astype("int64")
)

DDL = [
    "DROP TABLE IF EXISTS events",
    """CREATE TABLE events (
    user_id    UInt32,
    event_date Date,
    event_ts   DateTime,
    event_type UInt8,
    product_id UInt16,
    channel    UInt8,
    amount     Float32
) ENGINE = MergeTree
PARTITION BY toYYYYMM(event_date)
ORDER BY (event_date, user_id)""",
]

INSERT = """
INSERT INTO events (user_id, event_date, event_ts, event_type, product_id, channel, amount)
SELECT user_id, toDate(event_ts), toDateTime(event_ts),
       event_type, product_id, channel, amount
FROM file('seed.parquet', Parquet)
SETTINGS max_insert_threads = 4;
"""


def gen_parquet() -> None:
    if PARQUET.exists():
        print(
            f"{PARQUET} exists ({PARQUET.stat().st_size / 1e6:.0f} MB), skip generation"
        )
        return
    rng = np.random.default_rng(42)
    user_id = rng.integers(1, 1_000_001, N, dtype=np.uint32)
    # Bursty activity: every (user, slot) pair maps deterministically to one day and one
    # hour cluster, so a user's ~50 events fall into ~15 sessions of a few events each.
    # With uniform seconds every event would be its own 30-min session and case 03 would
    # be degenerate (1.01 events/session).
    slot = rng.integers(0, 15, N, dtype=np.int64)
    u = user_id.astype(np.int64)
    day = ((u * 2654435761 + slot * 40503) % 180).astype(np.int16)
    hour = ((u * 40503 + slot * 2654435761) % 24).astype(np.int32)
    sec = (hour * 3600 + rng.exponential(900, N).clip(0, 3599)).astype(np.int32)
    # event_type: 50% visit, 20% cart, 12% checkout, 18% purchase
    event_type = np.searchsorted([0.50, 0.70, 0.82], rng.random(N)).astype(np.uint8) + 1
    product_id = rng.integers(1, 1001, N, dtype=np.uint16)
    # channel: [0.35, 0.25, 0.20, 0.10, 0.10]
    channel = (np.searchsorted([0.35, 0.60, 0.80, 0.90], rng.random(N)) + 1).astype(
        np.uint8
    )
    amount = np.where(event_type == 4, rng.uniform(5, 500, N), 0.0).astype(np.float32)
    event_ts = (EPOCH + day.astype(np.int64) * 86_400 + sec).astype("datetime64[s]")

    df = pd.DataFrame(
        {
            "user_id": user_id,
            "event_ts": event_ts,
            "event_type": event_type,
            "product_id": product_id,
            "channel": channel,
            "amount": amount,
        }
    )
    PARQUET.parent.mkdir(exist_ok=True)
    con = duckdb.connect()
    con.register("copy_events", df)
    con.execute(
        "COPY (SELECT * FROM copy_events) TO '"
        + str(PARQUET)
        + "' (FORMAT PARQUET, COMPRESSION ZSTD)"
    )
    con.unregister("copy_events")
    print(f"seed.parquet written: {PARQUET.stat().st_size / 1e6:.0f} MB, {N:,} rows")


def load_clickhouse() -> None:
    client = clickhouse_connect.get_client(
        host="localhost", port=8123, username="default", password="lab"
    )
    for stmt in DDL:
        client.command(stmt)
    client.command(INSERT)
    n = client.query("SELECT count() FROM events").result_rows[0][0]
    print(f"events: {n:,} rows in ClickHouse")
    assert n == N, f"expected {N:,}, got {n:,}"


def main() -> None:
    gen_parquet()
    load_clickhouse()


if __name__ == "__main__":
    main()

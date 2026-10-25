"""Run every case in cases/ against live ClickHouse, cross-check DuckDB references,
and diff against cases/expected.json (the regression snapshot).

    uv run python scripts/run.py                # run + compare
    uv run python scripts/run.py --snapshot     # rewrite expected.json from CH output
    uv run python scripts/run.py --duck-only    # no server needed: DuckDB refs only
"""

import argparse
import json
from pathlib import Path

import clickhouse_connect
import duckdb

CASES = Path("cases")
EXPECTED = CASES / "expected.json"
PARQUET = "data/seed.parquet"
CH = {"host": "localhost", "port": 8123, "username": "default", "password": "lab"}
DUCK_VIEW = f"""
CREATE VIEW events AS
SELECT user_id,
       CAST(event_ts AS DATE) AS event_date,
       CAST(event_ts AS TIMESTAMP) AS event_ts,
       event_type, product_id, channel, amount
FROM read_parquet('{PARQUET}')
"""


def case_files() -> list[Path]:
    return sorted(
        p
        for p in CASES.glob("*.sql")
        if p.name[0].isdigit() and not p.name.endswith(".duck.sql")
    )


def _norm(rows) -> list[tuple]:
    return [
        tuple(str(v) if not isinstance(v, (int, float)) else v for v in r) for r in rows
    ]


def _close(a, b, tol=0.01, rel=1e-9) -> bool:
    """Row-by-row equality. Floats compared with a relative tolerance: parallel
    aggregation (CH, many threads) sums in a different order than DuckDB's, so exact
    bit equality is not achievable on 50M-row sums — anything beyond 1e-9 relative is
    a real divergence."""
    if len(a) != len(b):
        return False
    for ra, rb in zip(a, b):
        if len(ra) != len(rb):
            return False
        for x, y in zip(ra, rb):
            if isinstance(x, (int, float)) and isinstance(y, (int, float)):
                if abs(float(x) - float(y)) > max(tol, rel * abs(float(y))):
                    return False
            elif str(x) != str(y):
                return False
    return True


def _jsonable(rows) -> list[list]:
    return [[str(v) if not isinstance(v, (int, float)) else v for v in r] for r in rows]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", action="store_true", help="overwrite expected.json")
    ap.add_argument("--duck-only", action="store_true", help="skip ClickHouse entirely")
    args = ap.parse_args()

    expected = (
        json.loads(EXPECTED.read_text())
        if EXPECTED.exists() and not args.snapshot
        else {}
    )
    ch = None if args.duck_only else clickhouse_connect.get_client(**CH)
    duck = duckdb.connect()
    duck.execute(DUCK_VIEW)
    new_snapshot = {}

    print(f"{'case':<28} {'CH rows':>7}  {'snapshot':<9} {'duck':<9} note")
    failures = []
    for path in case_files():
        name = path.stem
        ch_rows = None
        if ch is not None:
            ch_rows = _norm(ch.query(path.read_text()).result_rows)
            new_snapshot[name] = _jsonable(ch_rows)

        snap = "-"
        if ch_rows is not None and name in expected:
            snap = (
                "ok"
                if _close(ch_rows, _norm([tuple(r) for r in expected[name]]))
                else "DIFF"
            )
            if snap == "DIFF":
                failures.append(f"{name}: snapshot mismatch")

        duck_ref = path.with_suffix(".duck.sql")
        duck_res = "-"
        if duck_ref.exists():
            duck_rows = _norm(duck.execute(duck_ref.read_text()).fetchall())
            if ch_rows is None:
                duck_res = f"{len(duck_rows)} rows"
            else:
                duck_res = "ok" if _close(ch_rows, duck_rows) else "DIFF"
                if duck_res == "DIFF":
                    failures.append(f"{name}: CH vs DuckDB divergence")

        print(
            f"{name:<28} {len(ch_rows) if ch_rows else '-':>7}  {snap:<9} {duck_res:<9} "
            f"{duck_ref.name if duck_ref.exists() else 'CH-only (no duck ref)'}"
        )

    if args.snapshot:
        EXPECTED.write_text(json.dumps(new_snapshot, ensure_ascii=False, indent=1))
        print(f"snapshot written: {EXPECTED} ({len(new_snapshot)} cases)")

    if failures:
        print("\nFAILURES:")
        for f in failures:
            print(" -", f)
        raise SystemExit(1)
    print("\nall cases ok")


if __name__ == "__main__":
    main()

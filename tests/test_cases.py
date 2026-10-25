"""Live-ClickHouse checks: seed size, all cases vs snapshot + DuckDB refs, and the
optimization case's >=10x speedup.

Server-free checks live in ``tests/test_static.py`` and run in a plain ``pytest``.
Everything here needs the lab and is marked ``integration``:

    pytest                    # static suite only — passes with no docker
    pytest -m integration     # these tests (they skip when the lab is down)

To bring the lab up:

    docker compose up -d  &&  uv run python scripts/seed.py

Note: skips are per-test on purpose. A module-level ``pytestmark`` would skip the
whole file — including anything that needs no server — and leave ``pytest`` green
while proving nothing (see ``test_no_module_level_skip`` in tests/test_static.py).
"""

import statistics
import subprocess
import sys
import time
from functools import lru_cache
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
CASES = ROOT / "cases"
FIX = CASES / "10_optimization" / "fix.sql"
CH = {"host": "localhost", "port": 8123, "username": "default", "password": "lab"}


def _client():
    import clickhouse_connect

    return clickhouse_connect.get_client(**CH, connect_timeout=2)


@lru_cache(maxsize=1)
def _reachable() -> bool:
    try:
        _client().query("SELECT 1")
        return True
    except Exception:  # noqa: BLE001 — any driver error means "lab not running"
        return False


def _needs_lab(test):
    """Per-test marker: integration + skip when the lab is not running."""
    return pytest.mark.skipif(not _reachable(), reason="ClickHouse lab not running")(
        pytest.mark.integration(test)
    )


@pytest.fixture(scope="module")
def client():
    return _client()


@_needs_lab
def test_seed_row_count(client):
    assert client.query("SELECT count() FROM events").result_rows[0][0] == 50_000_000


def _sql(path: Path) -> str:
    """Strip -- comments so a single statement reaches the HTTP interface."""
    return "\n".join(
        line
        for line in path.read_text().splitlines()
        if not line.strip().startswith("--")
    )


@_needs_lab
def test_all_cases_match_snapshot_and_duckdb():
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "run.py")],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0, r.stdout + r.stderr
    assert "all cases ok" in r.stdout


@_needs_lab
def test_optimization_speedup(client):
    """>=10x from the projection. slow/fast SQL text is identical on purpose:
    the lever is schema-side, so the test measures the server before/after fix.sql."""
    slow_sql = _sql(CASES / "10_optimization" / "slow.sql")
    client.command("ALTER TABLE events DROP PROJECTION IF EXISTS p_product")

    def timed(sql: str, runs: int) -> float:
        client.query(sql)  # warm-up (page cache + query plan)
        ts = []
        for _ in range(runs):
            t0 = time.perf_counter()
            client.query(sql)
            ts.append(time.perf_counter() - t0)
        return statistics.median(ts)

    slow = timed(slow_sql, 3)

    for stmt in (s for s in _sql(FIX).split(";") if s.strip()):
        client.command(stmt)
    fast = timed(slow_sql, 5)  # identical SQL — the planner now reads p_product

    client.command("ALTER TABLE events DROP PROJECTION IF EXISTS p_product")
    speedup = slow / fast
    assert speedup >= 10, f"only {speedup:.1f}x (slow {slow:.3f}s, fast {fast:.3f}s)"

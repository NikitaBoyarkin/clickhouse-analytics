"""Static (no-server) checks over the case bank.

These run under a plain ``pytest`` with no docker and no ClickHouse running: they
bind the filesystem layout, ``cases/expected.json`` and `scripts/run.py`'s case
resolution to each other, so a green run on a reviewer's machine proves something
even when the lab is down. Server-dependent checks live in ``tests/test_cases.py``
behind ``-m integration``.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import os
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
CASES = ROOT / "cases"
OPT = CASES / "10_optimization"
EXPECTED = CASES / "expected.json"

# Words that show up in a comment block that actually names the metric being
# computed. Deliberately broad: the point is to catch an empty/stub case, not to
# enforce one wording per case.
METRIC_WORDS = (
    "funnel",
    "conversion",
    "retention",
    "session",
    "island",
    "streak",
    "top-",
    "top ",
    "revenue",
    "ltv",
    "attribution",
    "rfm",
    "cardinality",
    "uniq",
    "projection",
    "optimization",
)

PLACEHOLDER_RE = re.compile(r"\b(TODO|FIXME|XXX|TBD|placeholder)\b", re.IGNORECASE)

# Floor for "not a stub". The real bank ranges 5..28 code lines per file, so 4
# catches an empty skeleton while keeping headroom under the smallest real case
# (10_optimization/fix.sql, 5 code lines). A flat ">10" would reject three real
# cases, so it is not used here.
MIN_CODE_LINES = 4


def _expected() -> dict:
    return json.loads(EXPECTED.read_text(encoding="utf-8"))


def _numbered_cases() -> list[Path]:
    """Same filter scripts/run.py uses: top level, digit-leading, CH flavour only."""
    return sorted(
        p
        for p in CASES.glob("*.sql")
        if p.name[0].isdigit() and not p.name.endswith(".duck.sql")
    )


def _code_lines(path: Path) -> list[str]:
    """Lines that are not blank and not ``--`` comments (what a query engine sees)."""
    return [
        line
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("--")
    ]


def _code_text(path: Path) -> str:
    return "\n".join(_code_lines(path)).strip()


def _leading_comment(path: Path) -> list[str]:
    """The contiguous ``--`` block at the top of the file."""
    block: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not block and not line.strip():
            continue
        if line.strip().startswith("--"):
            block.append(line.strip())
        else:
            break
    return block


# --- snapshot <-> case files ------------------------------------------------


def test_expected_snapshot_matches_case_files():
    """Every runnable case has a snapshot entry, and no orphan keys survive."""
    cases = {p.stem for p in _numbered_cases()}
    snap = set(_expected())

    assert cases == snap, (
        f"snapshot drift — cases without snapshot: {sorted(cases - snap)}; "
        f"snapshot keys without a case file: {sorted(snap - cases)}"
    )


def test_snapshot_entries_are_non_empty_and_rectangular():
    """A snapshot truncated to ``[]`` or to ragged rows would make
    scripts/run.py's ``_close()`` compare nothing (or fail for the wrong reason)."""
    snap = _expected()
    assert snap, "expected.json is empty"
    for name, rows in snap.items():
        assert rows, f"{name}: snapshot entry is empty"
        assert all(isinstance(r, list) for r in rows), f"{name}: rows must be lists"
        widths = {len(r) for r in rows}
        assert len(widths) == 1, (
            f"{name}: ragged snapshot rows, widths={sorted(widths)}"
        )


# --- DuckDB cross-check twins ----------------------------------------------


def test_every_duck_twin_has_a_clickhouse_sibling():
    """``.duck.sql`` pairing is symmetric: no twin without the CH case it mirrors."""
    twins = sorted(CASES.glob("*.duck.sql"))
    assert twins, "all DuckDB cross-check twins disappeared"

    snap = set(_expected())
    for twin in twins:
        sibling = twin.with_name(twin.name.removesuffix(".duck.sql") + ".sql")
        assert sibling.exists(), f"{twin.name}: no ClickHouse sibling {sibling.name}"

        # scripts/run.py resolves the twin via path.with_suffix(".duck.sql"), so the
        # name must round-trip through exactly this convention.
        assert sibling.with_suffix(".duck.sql") == twin
        assert sibling.stem in snap, (
            f"{twin.name}: sibling {sibling.stem} has no expected.json entry"
        )


# --- case 10: the claim the >=10x speedup test rests on ---------------------


def test_optimization_lever_is_schema_side():
    fix = _code_text(OPT / "fix.sql")
    assert "ADD PROJECTION" in fix, "fix.sql no longer adds a projection"
    assert "MATERIALIZE PROJECTION" in fix, "fix.sql no longer materializes it"
    assert "ORDER BY product_id" in fix, "projection is not ordered by product_id"


def test_optimization_query_text_is_identical_slow_vs_fast():
    """The speedup test times ``slow.sql`` before and after ``fix.sql``; it never runs
    ``fast.sql``. So the case only holds if slow/fast carry the SAME query — the lever
    is schema-side. (fix.sql is DDL, not the query twin: it contains no revenue SELECT,
    which is why it is checked for the projection, not for query equality.)"""
    slow = _code_text(OPT / "slow.sql")
    fast = _code_text(OPT / "fast.sql")
    assert slow, "slow.sql is empty"
    assert slow == fast, (
        "slow.sql and fast.sql diverged — the speedup would be a rewrite"
    )


# --- no empty/placeholder cases --------------------------------------------


@pytest.mark.parametrize(
    "path", _numbered_cases() + sorted(OPT.glob("*.sql")), ids=lambda p: p.name
)
def test_case_declares_its_metric_in_a_leading_comment(path):
    """The ClickHouse case (not its DuckDB reference) must say in its header what it
    computes — a stub with an empty header is the failure mode this catches."""
    block = _leading_comment(path)
    assert len(block) >= 2, f"{path.name}: missing a leading comment block"
    assert any(word in " ".join(block).lower() for word in METRIC_WORDS), (
        f"{path.name}: leading comment block names no metric ({block[0]!r})"
    )

    text = path.read_text(encoding="utf-8")
    assert not PLACEHOLDER_RE.search(text), (
        f"{path.name}: placeholder marker left in file"
    )


@pytest.mark.parametrize("path", sorted(CASES.glob("*.sql")), ids=lambda p: p.name)
def test_case_file_names_its_own_case_id(path):
    """First comment line must name the case, so a copy-paste cannot leave the header
    of case 03 on top of the SQL of case 07. CH cases say ``-- 02: …``, DuckDB twins
    say ``-- DuckDB reference for 02 …`` — both must carry the id."""
    first = _leading_comment(path)[0]
    prefix = path.name.split("_", 1)[0]
    assert re.match(rf"^--.*\b{prefix}\b", first), f"{path.name}: header is {first!r}"


@pytest.mark.parametrize(
    "path",
    sorted(CASES.glob("*.sql")) + sorted(OPT.glob("*.sql")),
    ids=lambda p: p.name,
)
def test_case_is_non_trivial(path):
    code = _code_lines(path)
    assert len(code) >= MIN_CODE_LINES, (
        f"{path.name}: only {len(code)} code lines — looks like a stub"
    )
    assert any("select" in line.lower() for line in code), f"{path.name}: no SELECT"


# --- run.py resolves the same set as the snapshot ---------------------------


def test_run_py_resolves_the_same_case_set_as_expected_json():
    """The snapshot is only a regression guard for the cases run.py actually runs."""
    spec = importlib.util.spec_from_file_location(
        "clickhouse_lab_run", ROOT / "scripts" / "run.py"
    )
    assert spec and spec.loader
    run = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(run)
    run.CASES = CASES

    resolved = {p.stem for p in run.case_files()}
    snap = set(_expected())
    assert resolved == snap, (
        f"run.py/cases/expected.json disagree — run.py only: {sorted(resolved - snap)}; "
        f"snapshot only: {sorted(snap - resolved)}"
    )


# --- anti-vacuity ratchet ---------------------------------------------------


def _module_level_pytestmark(path: Path) -> str | None:
    """Return a description of a module-level skip, or None. Per-test decorators
    (``@pytest.mark.skipif`` on a ``def``) are allowed and invisible here."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in tree.body:
        targets = []
        if isinstance(node, ast.Assign):
            targets = node.targets
        elif isinstance(node, ast.AnnAssign):
            targets = [node.target]

        for target in targets:
            if isinstance(target, ast.Name) and target.id == "pytestmark":
                return f"{path.name}:{node.lineno}: module-level `pytestmark = …`"

        if (
            isinstance(node, ast.Expr)
            and isinstance(node.value, ast.Call)
            and ast.unparse(node.value.func) in {"pytest.skip", "pytest.importorskip"}
        ):
            return f"{path.name}:{node.lineno}: module-level `{ast.unparse(node.value.func)}(…)`"
    return None


def _ratchet_targets() -> list[Path]:
    override = os.environ.get("STATIC_RATCHET_TARGET")
    if override:
        return [Path(override)]
    return sorted(Path(__file__).parent.glob("test_*.py"))


@pytest.mark.parametrize("path", _ratchet_targets(), ids=lambda p: p.name)
def test_no_module_level_skip(path):
    """A module-level skip silently turns the whole file green-without-proof: that is
    exactly the defect this suite was split to fix. Skipping must be per-test."""
    violation = _module_level_pytestmark(path)
    assert violation is None, (
        f"{violation} — move the skip onto the tests that need the server "
        "(see tests/test_cases.py)"
    )


def test_static_suite_needs_no_server():
    """This module must stay importable without a ClickHouse client or a test-module
    import that would drag the integration module (and its connect attempt) in."""
    source = Path(__file__).read_text(encoding="utf-8")
    for needle in ("clickhouse" + "_connect", "import " + "test_cases"):
        assert needle not in source, f"{needle} leaked into the static suite"

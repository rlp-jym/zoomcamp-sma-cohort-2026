"""Reconciliation budget (B6).

The ingestion chain is only trustworthy while the reported price of every holding matches
the market. This is the guard that fails the build when that stops being true.

Run: cd project_1 && uv run pytest -q
"""

from __future__ import annotations

import pytest

from breadth import verify

# tolerate a little drift; anything bigger means a parse or mapping regression
MAX_MISMATCH_WEIGHT = 1.0  # percent of portfolio weight
MIN_COVERAGE_WEIGHT = 80.0  # percent, for the periods we actually model


@pytest.fixture(scope="module")
def reconciled():
    try:
        return verify.reconcile()
    except SystemExit as exc:
        pytest.skip(str(exc))


def test_mismatched_weight_is_under_one_percent(reconciled) -> None:
    share = verify.mismatch_share(reconciled)
    assert share < MAX_MISMATCH_WEIGHT, f"{share:.2f}% of weight does not reconcile"


def test_modern_periods_have_enough_coverage(reconciled) -> None:
    rep = verify.report(reconciled)
    modern = rep.loc[rep.index >= "2016-01-01"]
    assert not modern.empty
    assert modern["coverage_weight"].min() >= MIN_COVERAGE_WEIGHT


def test_every_period_reports_both_weight_measures(reconciled) -> None:
    rep = verify.report(reconciled)
    assert list(rep.columns) == [
        "holdings",
        "coverage_names",
        "match_names",
        "coverage_weight",
        "match_weight",
    ]
    assert (rep["match_weight"] <= rep["coverage_weight"] + 1e-9).all()


def test_mismatch_share_is_zero_or_tiny(reconciled) -> None:
    # tighter than the CI budget: the current state is fully reconciled
    assert verify.mismatch_share(reconciled) == 0.0

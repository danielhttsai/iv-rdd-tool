"""Tests for the Trend-in-trend core and assumptions."""
import numpy as np

import tit_gen
import tit_core
import tit_assumptions


def test_recovers_true_or_and_naive_is_biased():
    df = tit_gen.generate()
    out = tit_core.full_tit(df, lang="zh")
    # trend-in-trend recovers the true OR (2.0) more closely than the naive cohort OR
    assert abs(out["or"] - tit_gen.TRUE_OR) < 0.6
    assert out["naive_or"] > tit_gen.TRUE_OR + 0.3      # naive is biased upward
    assert abs(out["or"] - tit_gen.TRUE_OR) < abs(out["naive_or"] - tit_gen.TRUE_OR)
    assert out["converged"]
    assert out["outcome_rate"] < 0.05                   # rare outcome


def test_exposure_trend_present():
    df = tit_gen.generate()
    out = tit_core.full_tit(df, lang="zh")
    assert out["exposure_overall"][-1] - out["exposure_overall"][0] > 0.10


def test_weak_trend_collapses_identification():
    strong = tit_core.full_tit(tit_gen.generate(trend=1.0))
    weak = tit_core.full_tit(tit_gen.generate(trend=0.25))
    # a strong trend recovers ~2.0; a near-flat trend cannot
    assert abs(strong["or"] - 2.0) < abs(weak["or"] - 2.0) + 1e-9


def test_dashboard_shape_and_statuses():
    df = tit_gen.generate()
    dash = tit_assumptions.run_dashboard(df, lang="zh")
    ids = [c["id"] for c in dash["checks"]]
    assert ids == ["A1", "A2", "A3", "A4", "A5"]
    for c in dash["checks"]:
        assert c["status"] in ("green", "amber", "red", "info")
        assert c["title"] and c["headline"] and c["plain"] and c["term"]
    assert dash["checks"][0]["status"] == "green"        # strong trend -> A1 green
    assert dash["checks"][3]["status"] == "info"         # A4 untestable
    weak = tit_assumptions.run_dashboard(tit_gen.generate(trend=0.25), lang="zh")
    assert weak["checks"][0]["status"] in ("amber", "red")


def test_bilingual_interpretation():
    df = tit_gen.generate()
    zh = tit_core.full_tit(df, lang="zh")
    en = tit_core.full_tit(df, lang="en")
    assert zh["interpretation"] != en["interpretation"]
    assert "OR" in en["interpretation"]

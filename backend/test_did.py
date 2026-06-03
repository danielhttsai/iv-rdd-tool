"""Snapshot-style tests for the Difference-in-differences core, assumptions and ⑤ demos."""
import numpy as np

import did_gen
import did_core
import did_assumptions
import did_ml


def test_2x2_and_regression_recover_true_att():
    df = did_gen.generate()
    out = did_core.full_did(df, "unit", "period", "treated", "health_score", t0=3)
    # both the 2x2 and the regression b3 should recover the true ATT (3.0) within noise
    assert abs(out["two_by_two"]["did"] - did_gen.TRUE_ATT) < 0.5
    assert abs(out["did"]["estimate"] - did_gen.TRUE_ATT) < 0.5
    assert out["did"]["se"] > 0
    # the naive post-only gap is biased away from the truth
    assert abs(out["naive_difference"] - did_gen.TRUE_ATT) > 0.5


def test_event_study_pretrend_clean_when_parallel():
    df = did_gen.generate()
    ev = did_core.event_study(df, "treated", "period", "health_score", 3, "unit")
    # base period coefficient is fixed to 0
    assert ev["coef"][ev["periods"].index(ev["base"])] == 0.0
    # parallel-trends hold -> no significant pre-trend
    assert ev["pre_max_p"] >= 0.05


def test_event_study_detects_violation():
    df = did_gen.generate(violation=0.9)
    ev = did_core.event_study(df, "treated", "period", "health_score", 3, "unit")
    # a real pre-trend should be flagged
    assert ev["pre_max_p"] < 0.05


def test_dashboard_shape_and_statuses():
    df = did_gen.generate()
    dash = did_assumptions.run_dashboard(df, "unit", "period", "treated", "health_score", t0=3)
    ids = [c["id"] for c in dash["checks"]]
    assert ids == ["D1", "D2", "D3", "D4", "D5"]
    for c in dash["checks"]:
        assert c["status"] in ("green", "amber", "red", "info")
        assert c["title"] and c["headline"] and c["plain"] and c["term"]
    # parallel version: D1 should pass
    assert dash["checks"][0]["status"] == "green"
    # violation version: D1 should fail
    bad = did_assumptions.run_dashboard(did_gen.generate(violation=0.9),
                                        "unit", "period", "treated", "health_score", t0=3)
    assert bad["checks"][0]["status"] == "red"


def test_variant_demos():
    d = did_ml.variant_demos(seed=7)
    assert set(d) == {"staggered", "universal", "synth"}
    # cohort-time average beats TWFE
    assert abs(d["staggered"]["cs"] - d["staggered"]["true_att"]) < abs(d["staggered"]["twfe"] - d["staggered"]["true_att"])
    # universal DiD recovers the true odds ratio closely
    assert abs(d["universal"]["or_did"] - d["universal"]["true_or"]) < 0.2
    # synthetic control lands near the true effect
    assert abs(d["synth"]["estimate"] - d["synth"]["true_effect"]) < 1.5


def test_dml_real_ml_beats_linear():
    d = did_ml.dml_demo(seed=7)
    # genuine ML (gradient boosting + cross-fitting) recovers the ATT under non-linear
    # confounding, closer than both the naive DiD and the linear doubly-robust version
    assert abs(d["ml"] - d["true_att"]) < abs(d["naive"] - d["true_att"])
    assert abs(d["ml"] - d["true_att"]) < abs(d["linear"] - d["true_att"])
    assert abs(d["ml"] - d["true_att"]) < 1.0


def test_bilingual_interpretation():
    df = did_gen.generate()
    zh = did_core.full_did(df, "unit", "period", "treated", "health_score", t0=3, lang="zh")
    en = did_core.full_did(df, "unit", "period", "treated", "health_score", t0=3, lang="en")
    assert "DiD" in en["did"]["interpretation"] or "difference" in en["did"]["interpretation"].lower()
    assert zh["did"]["interpretation"] != en["did"]["interpretation"]

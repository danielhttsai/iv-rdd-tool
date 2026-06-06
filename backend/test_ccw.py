"""Tests for the Clone-Censor-Weight core and assumptions."""
import numpy as np

import ccw_gen
import ccw_core
import ccw_assumptions


import pytest


@pytest.mark.parametrize("scenario", ["grace", "earlylate", "sustained"])
def test_ccw_recovers_truth_and_naive_is_biased(scenario):
    df = ccw_gen.generate(scenario=scenario)
    out = ccw_core.full_ccw(df, scenario=scenario)
    truth = out["true_rd"]
    # CCW lands near the estimand's truth; the naive contrast is clearly more biased
    assert abs(out["ccw"] - truth) < 0.05
    assert abs(out["naive"] - truth) > abs(out["ccw"] - truth) + 0.05
    assert out["ccw"] < -0.05                       # arm-1 strategy is protective
    for arm in ("early", "late"):                   # cumulative-incidence monotone
        c = out["curve"][arm]
        assert all(c[i + 1] >= c[i] - 1e-9 for i in range(len(c) - 1))
    assert out["curve"]["early"][-1] < out["curve"]["late"][-1]


@pytest.mark.parametrize("scenario", ["grace", "earlylate", "sustained"])
def test_truth_grid_monotone_in_timing_effect(scenario):
    # stronger protective timing effect → more negative (more protective) truth
    vals = [ccw_core.estimand_truth(te, scenario=scenario) for te in (0.0, 0.25, 0.5, 0.75, 1.0)]
    assert all(vals[i + 1] < vals[i] for i in range(len(vals) - 1))
    assert vals[0] > -0.05            # no effect → risk difference ≈ 0
    assert vals[-1] < -0.05           # full effect → protective


def test_interactive_tracks_truth():
    # with the slider at a few settings, CCW should track the (changing) truth
    for te in (0.0, 0.5, 1.0):
        df = ccw_gen.generate(n=5000, timing_effect=te)
        out = ccw_core.full_ccw(df, true_rd=ccw_core.estimand_truth(te))
        assert abs(out["ccw"] - out["true_rd"]) < 0.06


def test_dashboard_shape_and_statuses():
    df = ccw_gen.generate()
    dash = ccw_assumptions.run_dashboard(df)
    ids = [c["id"] for c in dash["checks"]]
    assert ids == ["C1", "C2", "C3", "C4", "C5"]
    for c in dash["checks"]:
        assert c["status"] in ("green", "amber", "red", "info")
        assert c["title"] and c["headline"] and c["plain"] and c["term"]
    assert dash["checks"][0]["status"] == "info"     # C1 exchangeability untestable
    assert dash["checks"][4]["status"] == "info"     # C5 alignment by design


def test_grace_weights_are_stabilized():
    # grace / early-vs-late use STABILIZED weights → average ≈ 1
    out = ccw_core.full_ccw(ccw_gen.generate())
    for arm in ("early", "late"):
        w = out["weights"][arm]
        assert 0.7 < w["mean"] < 1.5         # stabilized weights average ≈ 1
        assert w["max"] < 50


def test_sustained_weights_are_unstabilized():
    # sustained (stay-on vs discontinue) uses UNSTABILIZED weights (numerator = 1)
    # → 1/uncensored-probability, so the mean is clearly above 1 (not stabilized)
    out = ccw_core.full_ccw(ccw_gen.generate(scenario="sustained"), scenario="sustained")
    means = [out["weights"][arm]["mean"] for arm in ("early", "late")]
    assert max(means) > 1.6              # at least one arm's mean is well above 1
    # and the design still recovers the truth despite the larger, truncated weights
    truth = ccw_core.estimand_truth(1.0, scenario="sustained")
    assert abs(out["ccw"] - truth) < 0.05
    assert abs(out["naive"] - truth) > abs(out["ccw"] - truth) + 0.05


@pytest.mark.parametrize("scenario", ["grace", "earlylate", "sustained"])
def test_grace_demo_shape_and_sensitivity(scenario):
    s = ccw_core.grace_demo(scenario=scenario)
    assert s["graces"] == [1, 2, 3, 4, 5]
    assert len(s["ccw"]) == 5 and len(s["naive"]) == 5
    # naive stays clearly more biased than CCW at the reference grace (g=3, index 2)
    assert abs(s["naive"][2] - s["truth_ref"]) > abs(s["ccw"][2] - s["truth_ref"])


def test_bilingual_interpretation():
    df = ccw_gen.generate()
    zh = ccw_core.full_ccw(df, lang="zh")
    en = ccw_core.full_ccw(df, lang="en")
    assert zh["interpretation"] != en["interpretation"]
    assert "CCW" in en["interpretation"] or "clone" in en["interpretation"].lower()

"""Tests for the Active-Comparator, New-User (ACNU) method."""
from __future__ import annotations

import acnu_gen
import acnu_core
import acnu_assumptions


def test_acnu_recovers_truth_and_naive_is_biased():
    df = acnu_gen.generate()
    r = acnu_core.full_acnu(df)
    truth = r["true_hr"]
    # severity-adjusted ACNU lands near the truth
    assert abs(r["adj_irr"] - truth) < 0.15
    # the naive A-vs-non-user contrast is clearly more biased than adjusted ACNU
    assert abs(r["naive_irr"] - truth) > abs(r["adj_irr"] - truth) + 0.8
    # crude ACNU (active comparator) is less biased than the naive contrast
    assert abs(r["crude_irr"] - truth) < abs(r["naive_irr"] - truth)
    # active comparator B is closer in severity to A than non-users are
    bal = r["severity_balance"]
    assert abs(bal["A"] - bal["B"]) < abs(bal["A"] - bal["none"])


def test_interactive_grid_monotone():
    # naive bias and crude ACNU both grow with confounding; adjusted stays near truth
    naive = acnu_core._GRID["naive"]
    crude = acnu_core._GRID["crude"]
    adj = acnu_core._GRID["adj"]
    assert crude[-1] > crude[0] + 1.0                      # crude drifts up with confounding
    assert all(abs(a - 1.6) < 0.12 for a in adj)           # adjusted holds the truth
    assert all(n > 2.5 for n in naive)                     # naive is always badly biased


def test_interactive_endpoint_tracks_truth():
    lo = acnu_core.acnu_interactive(0.0)
    hi = acnu_core.acnu_interactive(1.5)
    assert abs(lo["adj_irr"] - lo["true_hr"]) < 0.12
    assert abs(hi["adj_irr"] - hi["true_hr"]) < 0.12
    assert hi["crude_irr"] > lo["crude_irr"] + 0.8         # crude ACNU drifts with conf


def test_dashboard_shape_and_statuses():
    df = acnu_gen.generate()
    dash = acnu_assumptions.run_dashboard(df)
    checks = dash["checks"]
    assert [c["id"] for c in checks] == ["C1", "C2", "C3", "C4", "C5"]
    for c in checks:
        assert c["status"] in ("green", "amber", "red", "info")
        assert c["headline"] and c["plain"]


def test_bilingual_interpretation():
    df = acnu_gen.generate()
    zh = acnu_core.full_acnu(df, lang="zh")
    en = acnu_core.full_acnu(df, lang="en")
    assert zh["interpretation"] != en["interpretation"]


def test_ml_ps_beats_logistic():
    import acnu_ml
    r = acnu_ml.ps_ml_demo()
    truth = r["true_hr"]
    # gradient-boosting PS recovers the truth better than a mis-specified logistic PS
    assert abs(r["irr_gb"] - truth) < abs(r["irr_logistic"] - truth)
    assert abs(r["irr_gb"] - truth) < 0.2
    # and both adjust away a big chunk of the crude/unadjusted bias
    assert abs(r["irr_unadj"] - truth) > abs(r["irr_gb"] - truth) + 1.0

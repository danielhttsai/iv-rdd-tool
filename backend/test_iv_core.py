"""Snapshot tests: the ported analysis reproduces the synthetic demo's design.

The built-in demo is fictional; its design (true LATE 1.80, ~9% compliers,
confounding-inflated naive ~2.60) is what these tests pin down.
"""
import iv_core
from gen_data import generate, COVARIATES

Y, A, Z = "health_score_change", "vaccinated", "vaccine_voucher"


def _df():
    return generate()  # fixed SEED/N -> deterministic


def test_naive_is_confounded_upward():
    df = _df()
    res = iv_core.naive_regression(df, Y, A, COVARIATES)
    assert abs(res["estimate"] - 2.60) < 0.15   # biased above the true 1.80


def test_first_stage_compliers():
    df = _df()
    fs = iv_core.first_stage(df, A, Z)
    assert abs(fs["coef"] - 0.090) < 0.01        # ~9% compliers
    assert fs["f_stat"] > 10                      # strong instrument


def test_iv_recovers_true_late():
    df = _df()
    iv = iv_core.iv_2sls(df, Y, A, Z)
    assert abs(iv["estimate"] - 1.80) < 0.15      # true LATE = 1.80


def test_iv_below_naive():
    df = _df()
    naive = iv_core.naive_regression(df, Y, A, COVARIATES)["estimate"]
    iv = iv_core.iv_2sls(df, Y, A, Z)["estimate"]
    assert iv < naive                              # confounding inflates naive


def test_wald_equals_2sls_uncovaried():
    df = _df()
    wald = iv_core.wald_estimator(df, Y, A, Z)
    iv = iv_core.iv_2sls(df, Y, A, Z)
    assert abs(wald["estimate"] - iv["estimate"]) < 1e-6


def test_manual_two_stage_equals_wald():
    df = _df()
    wald = iv_core.wald_estimator(df, Y, A, Z)
    ts = iv_core.two_stage_manual(df, Y, A, Z)
    assert abs(ts["estimate"] - wald["estimate"]) < 1e-6


def test_full_analysis_payload_shape():
    df = _df()
    out = iv_core.full_analysis(df, Y, A, Z, COVARIATES)
    for key in ("naive", "first_stage", "reduced_form", "wald", "iv", "iv_with_covariates"):
        assert key in out
    assert out["iv_with_covariates"] is not None

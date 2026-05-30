"""Machine-learning + IV demonstrations (tab 5), vaccine story.

Plain-language goal: on the SAME vaccine example, show the two honest things ML
can do for an instrumental-variable analysis, plus the one safety rule. Pure
numpy/scipy so it runs anywhere.

Themes (mapped to the papers the user added), each demonstrated with numbers
that hold up across the interactive sliders:

  藥方一  合成工具 (synthesis): many candidate nudges, each individually a WEAK
          instrument, can be combined by ML into ONE strong synthesised
          instrument.                         (MLIV synthesis; Peng 2024 §resilience)
  藥方二  可彎的第一階段 (flexible first stage): when an instrument's relevance is
          curved (not a straight line), a straight-line first stage misses it
          entirely, but a flexible ML first stage finds it. (Bruns-Smith 2025; boostIV)
  安全帶  交叉擬合 (cross-fitting): we always predict out-of-fold so the first
          stage cannot "peek" at the same rows it is later used on. This is the
          guard against the forbidden-regression / overfitting trap. (Peng 2024)

Vaccine scenario:  Z = quasi-random nudges,  A = vaccinated,
Y = health-score change,  U = unobserved health consciousness (the confounder).
"""
from __future__ import annotations

import numpy as np

TRUE_LATE = 1.80


# ---------------------------------------------------------------------------
# Linear-algebra helpers (no statsmodels)
# ---------------------------------------------------------------------------
def _ols_beta(X, y):
    return np.linalg.pinv(X.T @ X) @ (X.T @ y)


def _single_F(A, z):
    """First-stage F for ONE instrument z (regress A ~ const + z); F == t^2."""
    n = len(A)
    X = np.column_stack([np.ones(n), z])
    beta = _ols_beta(X, A)
    resid = A - X @ beta
    rss = float(resid @ resid)
    dof = n - 2
    if dof <= 0 or rss <= 0:
        return 0.0
    sigma2 = rss / dof
    se = np.sqrt(sigma2 * np.linalg.pinv(X.T @ X)[1, 1])
    t = beta[1] / se if se > 0 else 0.0
    return float(t * t)


def _tsls(Y, A, Z, cov=None):
    """2SLS of Y on [const, A, cov] instrumented by [const, Z, cov].

    Z may be a single column (n,) or a matrix (n, q). Returns estimate, se, CI.
    """
    n = len(Y)
    const = np.ones(n)
    Z = np.asarray(Z, dtype=float)
    if Z.ndim == 1:
        Z = Z[:, None]
    cov = np.empty((n, 0)) if cov is None else np.asarray(cov, dtype=float)
    if cov.ndim == 1:
        cov = cov[:, None]

    X = np.column_stack([const, A, cov])
    Inst = np.column_stack([const, Z, cov])

    PzX = Inst @ (np.linalg.pinv(Inst.T @ Inst) @ (Inst.T @ X))
    A_mat = PzX.T @ X
    beta = np.linalg.pinv(A_mat) @ (PzX.T @ Y)
    resid = Y - X @ beta
    k = X.shape[1]
    dof = n - k
    sigma2 = float(resid @ resid) / dof if dof > 0 else float("nan")
    covb = sigma2 * np.linalg.pinv(A_mat)
    se = np.sqrt(np.diag(covb))
    est = float(beta[1])
    s = float(se[1])
    return {"estimate": est, "se": s, "ci": [est - 1.96 * s, est + 1.96 * s]}


def _crossfit_instrument(A, Phi, k_folds=5, seed=0):
    """Out-of-fold fitted treatment = an honestly synthesised single instrument.

    Phi is the feature matrix (n, m) WITHOUT a constant. We fit the first stage
    on the OTHER folds and predict on the held-out fold, so the synthesised
    instrument never peeks at the rows it is later used on (cross-fitting).
    """
    n = len(A)
    rng = np.random.default_rng(seed)
    idx = rng.permutation(n)
    folds = np.array_split(idx, k_folds)
    zhat = np.empty(n)
    design = np.column_stack([np.ones(n), Phi])
    for f in folds:
        mask = np.ones(n, dtype=bool)
        mask[f] = False
        beta = _ols_beta(design[mask], A[mask])
        zhat[f] = design[f] @ beta
    return zhat


def _poly_basis(x, degree=6):
    x = (np.asarray(x, dtype=float) - np.mean(x)) / (np.std(x) + 1e-9)
    return np.column_stack([x ** d for d in range(1, degree + 1)])


# ---------------------------------------------------------------------------
# Data-generating processes (vaccine story) — tuned so the teaching numbers
# behave robustly across the interactive slider ranges.
# ---------------------------------------------------------------------------
def _gen_weak_candidates(n, k_candidates, per_strength, seed):
    """Many candidate nudges, each individually weak; combined can be strong.

    Story: voucher mailed, clinic flyer, employer reminder, community
    announcement ... each only weakly moves vaccination, all quasi-random.
    p is centred at 0.5 so it stays safely inside (0,1) (no clipping artefacts).
    """
    rng = np.random.default_rng(seed)
    U = rng.standard_normal(n)  # unobserved health consciousness (confounder)
    Z = rng.binomial(1, 0.5, size=(n, k_candidates)).astype(float)
    centred = Z.sum(axis=1) - k_candidates / 2.0
    p = 0.50 + per_strength * centred + 0.06 * U
    p = np.clip(p, 0.02, 0.98)
    A = rng.binomial(1, p).astype(float)
    Y = 2.0 + TRUE_LATE * A + 1.50 * U + rng.normal(0, 3.0, n)
    return Y, A, Z


def _gen_nonlinear_candidate(n, seed):
    """One CONTINUOUS candidate whose relevance is a hump (non-monotone).

    Story: a pop-up vaccine van parks at a roving location; "distance to today's
    van" matters most at a middle sweet-spot and tails off at both ends. A
    straight-line first stage sees almost no correlation; a flexible one sees the
    hump.
    """
    rng = np.random.default_rng(seed)
    U = rng.standard_normal(n)
    dist = rng.uniform(0, 10, n)  # km to today's pop-up van
    nudge = 0.32 * np.exp(-((dist - 5.0) / 1.3) ** 2)  # peak at 5 km, ~0 at ends
    p = 0.40 + (nudge - 0.16) + 0.05 * U  # subtract mean nudge to keep p centred
    p = np.clip(p, 0.02, 0.98)
    A = rng.binomial(1, p).astype(float)
    Y = 2.0 + TRUE_LATE * A + 1.50 * U + rng.normal(0, 3.0, n)
    return Y, A, dist


# ---------------------------------------------------------------------------
# Public: synthesis demo (藥方一) — drives sliders (# candidates, per-strength)
# ---------------------------------------------------------------------------
def synthesis_demo(n=6000, k_candidates=12, per_strength=0.03, seed=7):
    n = int(np.clip(n, 1000, 20000))
    k_candidates = int(np.clip(k_candidates, 2, 20))
    per_strength = float(np.clip(per_strength, 0.005, 0.08))
    Y, A, Z = _gen_weak_candidates(n, k_candidates, per_strength, seed)

    per_F = [round(_single_F(A, Z[:, j]), 1) for j in range(k_candidates)]

    # (1) Use ONE candidate only -> weak instrument: wide, unreliable.
    single = _tsls(Y, A, Z[:, 0])
    single["f_stat"] = round(_single_F(A, Z[:, 0]), 1)

    # (2) ML synthesis: cross-fitted single instrument -> strong + honest.
    zhat = _crossfit_instrument(A, Z, k_folds=5, seed=seed)
    mliv = _tsls(Y, A, zhat)
    mliv["f_stat"] = round(_single_F(A, zhat), 1)

    return {
        "true_late": TRUE_LATE,
        "n": n,
        "k_candidates": k_candidates,
        "per_strength": per_strength,
        "per_candidate_F": per_F,
        "max_single_F": round(max(per_F), 1) if per_F else None,
        "single_weak": single,
        "mliv_crossfit": mliv,
    }


# ---------------------------------------------------------------------------
# Public: flexible first-stage demo (藥方二)
# ---------------------------------------------------------------------------
def nonlinear_demo(n=8000, seed=11):
    n = int(np.clip(n, 1000, 20000))
    Y, A, dist = _gen_nonlinear_candidate(n, seed)

    # Straight-line first stage: A ~ const + dist (misses the hump -> weak).
    lin_F = _single_F(A, dist)
    zhat_lin = _crossfit_instrument(A, dist[:, None], k_folds=5, seed=seed)
    lin = _tsls(Y, A, zhat_lin)
    lin["f_stat"] = round(_single_F(A, zhat_lin), 1)

    # Flexible first stage: polynomial basis of dist, cross-fitted -> strong.
    Phi = _poly_basis(dist, degree=6)
    zhat_flex = _crossfit_instrument(A, Phi, k_folds=5, seed=seed)
    flex = _tsls(Y, A, zhat_flex)
    flex["f_stat"] = round(_single_F(A, zhat_flex), 1)

    # Curves for plotting. The straight-line fit is shown as-is (it is flat).
    # For the "flexible" curve we show the BINNED EMPIRICAL P(vaccinate) — i.e.
    # the actual hump in the data that a flexible learner recovers. This is both
    # honest (it is the data) and clean (no polynomial edge wiggles).
    nbins = 22
    edges = np.linspace(0, 10, nbins + 1)
    centres, bin_p = [], []
    for b in range(nbins):
        m = (dist >= edges[b]) & (dist < edges[b + 1] if b < nbins - 1 else dist <= edges[b + 1])
        if m.sum() > 0:
            centres.append((edges[b] + edges[b + 1]) / 2.0)
            bin_p.append(float(A[m].mean()))
    centres = np.array(centres)
    bl = _ols_beta(np.column_stack([np.ones(n), dist]), A)  # straight-line fit
    line_y = bl[0] + bl[1] * centres

    return {
        "true_late": TRUE_LATE,
        "n": n,
        "linear_first_stage_F": round(lin_F, 1),
        "flexible_first_stage_F": round(_single_F(A, zhat_flex), 1),
        "linear": lin,
        "flexible": flex,
        "curve": {
            "dist": centres.round(2).tolist(),
            "line": line_y.round(3).tolist(),
            "flex": [round(v, 3) for v in bin_p],
        },
    }


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def _gen_forbidden(n, seed, amp):
    """Multi-feature instruments with a smooth (no-clip) link, so the only way
    confounding leaks into the instrument is via OVERFITTING — which is exactly
    the forbidden-regression effect we want to expose.
    """
    rng = np.random.default_rng(seed)
    U = rng.standard_normal(n)  # unobserved confounder
    Z = rng.uniform(-2, 2, size=(n, 3))
    signal = np.tanh(Z[:, 0]) + np.sin(1.5 * Z[:, 1]) + 0.6 * Z[:, 2]
    p = _sigmoid(amp * signal + 0.55 * U)
    A = rng.binomial(1, p).astype(float)
    Y = 2.0 + TRUE_LATE * A + 1.50 * U + rng.normal(0, 3.0, n)
    return Y, A, Z


# ---------------------------------------------------------------------------
# Public: forbidden-regression demo (藥方三 — the live "trap vs safety belt")
# ---------------------------------------------------------------------------
def forbidden_demo(n=4000, seed=7, amp=1.2):
    """Same flexible model (random forest), two ways of using it.

    in-sample  : fit the first stage on ALL rows, predict on the SAME rows, plug
                 those fitted values in as the instrument -> overfits, leaks the
                 confounder back, estimate glued to the (biased) naive number.
    cross-fit  : fit on other folds, predict out-of-fold -> honest instrument,
                 estimate pulled back to the truth.
    """
    from sklearn.ensemble import RandomForestRegressor

    n = int(np.clip(n, 1500, 8000))
    Y, A, Z = _gen_forbidden(n, seed, amp)
    rf_kw = dict(n_estimators=100, min_samples_leaf=1, random_state=seed, n_jobs=-1)

    # naive (confounded) reference
    naive = float(_ols_beta(np.column_stack([np.ones(n), A]), Y)[1])

    # in-sample fitted instrument (the trap)
    zin = RandomForestRegressor(**rf_kw).fit(Z, A).predict(Z)
    trap = _tsls(Y, A, zin)
    trap["f_stat"] = round(_single_F(A, zin), 1)

    # cross-fitted instrument (the safety belt)
    rng = np.random.default_rng(seed)
    idx = rng.permutation(n)
    folds = np.array_split(idx, 5)
    zcf = np.empty(n)
    for f in folds:
        mask = np.ones(n, dtype=bool)
        mask[f] = False
        zcf[f] = RandomForestRegressor(**rf_kw).fit(Z[mask], A[mask]).predict(Z[f])
    honest = _tsls(Y, A, zcf)
    honest["f_stat"] = round(_single_F(A, zcf), 1)

    return {
        "true_late": TRUE_LATE,
        "n": n,
        "naive": round(naive, 2),
        "in_sample": {"estimate": round(trap["estimate"], 2),
                      "ci": [round(c, 2) for c in trap["ci"]], "f_stat": trap["f_stat"]},
        "cross_fit": {"estimate": round(honest["estimate"], 2),
                      "ci": [round(c, 2) for c in honest["ci"]], "f_stat": honest["f_stat"]},
    }


# ---------------------------------------------------------------------------
# Public: one consolidated comparison (bar chart — ties it all together)
# ---------------------------------------------------------------------------
def compare(seed=7):
    syn = synthesis_demo(seed=seed)
    nl = nonlinear_demo(seed=seed + 4)
    # naive OLS of Y on A (confounded) for reference, on the synthesis data.
    Y, A, _ = _gen_weak_candidates(syn["n"], syn["k_candidates"], syn["per_strength"], seed)
    n = len(Y)
    naive = float(_ols_beta(np.column_stack([np.ones(n), A]), Y)[1])

    bars = [
        {"label": "未調整（直接比較）", "estimate": round(naive, 2),
         "f": None, "status": "bad",
         "note": "被健康意識汙染，高估真正效果"},
        {"label": "單一弱工具", "estimate": round(syn["single_weak"]["estimate"], 2),
         "ci": [round(c, 2) for c in syn["single_weak"]["ci"]],
         "f": syn["single_weak"]["f_stat"], "status": "weak",
         "note": "工具太弱：估計亂跳、誤差範圍超寬"},
        {"label": "AI 合成工具", "estimate": round(syn["mliv_crossfit"]["estimate"], 2),
         "ci": [round(c, 2) for c in syn["mliv_crossfit"]["ci"]],
         "f": syn["mliv_crossfit"]["f_stat"], "status": "good",
         "note": "把多個弱外力揉成一個強外力，誤差大幅收窄"},
        {"label": "可彎的第一階段", "estimate": round(nl["flexible"]["estimate"], 2),
         "ci": [round(c, 2) for c in nl["flexible"]["ci"]],
         "f": nl["flexible"]["f_stat"], "status": "good",
         "note": "讓第一階段可以彎，抓到直線完全錯過的外力"},
    ]
    return {"true_late": TRUE_LATE, "bars": bars}

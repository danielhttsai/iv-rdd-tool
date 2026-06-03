"""Trend-in-trend (TiT) core — a from-scratch numpy/scipy reimplementation of the
identifying idea in Ji, Small, Leonard & Hennessy (2017, Epidemiology), suitable
for Pyodide (no external estimation packages, no copied package code).

白話：先用基線特徵算每個人的「累積暴露機率（CPE）」並分層；不同層的暴露盛行率隨時間
有不同的上升速度。若暴露真的致病，結果盛行率也會在『暴露上升快』的時間／層上升得快。
我們把資料整理成每（層 g × 時間 t）的格子，對格子層級的結果盛行率與暴露盛行率關係做
最大概似，識別因果勝算比 —— 這對『個體層的暴露-結果比較被未測混淆汙染』是穩健的。

Estimator (rare-outcome, multiplicative marginal model fitted on (g,t) cells):
    q_{gt} = exp(alpha_g + beta2 * t) * (1 + (exp(beta1) - 1) * p_{gt})
where
    q_{gt} = outcome prevalence in cell (g,t)        (modelled; O_{gt} ~ Binomial(N_{gt}, q))
    p_{gt} = exposure prevalence in cell (g,t)        (observed)
    alpha_g = stratum baseline log-risk (absorbs stratum-level confounding)
    beta2   = common secular trend in the unexposed baseline risk
    beta1   = causal log-odds-ratio ≈ log relative-risk (rare outcome)  -> OR = exp(beta1)
The effect is identified from how outcome prevalence tracks exposure prevalence ACROSS
time within strata — not from the confounded individual exposed-vs-unexposed contrast.

This is a faithful teaching reconstruction of the published design's identifying logic,
implemented independently; it is not the CRAN `TrendInTrend` package code.
"""
from __future__ import annotations

import numpy as np
from scipy import optimize

from i18n import t


# ---------------------------------------------------------------------------
# small numpy logistic regression (Newton) — for the CPE model
# ---------------------------------------------------------------------------
def _logit_fit(X, y, iters=30):
    beta = np.zeros(X.shape[1])
    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-(X @ beta)))
        W = p * (1 - p) + 1e-9
        grad = X.T @ (y - p)
        H = (X * W[:, None]).T @ X + 1e-8 * np.eye(X.shape[1])
        step = np.linalg.solve(H, grad)
        beta = beta + step
        if np.max(np.abs(step)) < 1e-9:
            break
    return beta


def cpe_strata(df, covariates, K=5):
    """Stage 1: cumulative probability of (ever) exposure from baseline covariates,
    split into K quantile strata. Returns a per-person stratum label (0..K-1)."""
    ever = df.groupby("pid")["exposed"].max()
    base = df.sort_values("period").groupby("pid").first()
    Xc = base[covariates].to_numpy(dtype=float)
    Xc = (Xc - Xc.mean(0)) / (Xc.std(0) + 1e-9)
    X = np.column_stack([np.ones(len(Xc)), Xc])
    y = ever.reindex(base.index).to_numpy(dtype=float)
    beta = _logit_fit(X, y)
    cpe = 1.0 / (1.0 + np.exp(-(X @ beta)))
    edges = np.quantile(cpe, np.linspace(0, 1, K + 1))
    edges[0] -= 1e-9
    strat = np.clip(np.digitize(cpe, edges) - 1, 0, K - 1)
    return dict(zip(base.index.tolist(), strat.tolist())), float(_auc(y, cpe))


def _auc(y, score):
    """Mann–Whitney AUC (c-statistic) for the CPE model quality."""
    pos = score[y == 1]
    neg = score[y == 0]
    if pos.size == 0 or neg.size == 0:
        return float("nan")
    # rank-based
    order = np.argsort(np.concatenate([pos, neg]))
    ranks = np.empty_like(order, dtype=float)
    ranks[order] = np.arange(1, order.size + 1)
    r_pos = ranks[:pos.size].sum()
    return (r_pos - pos.size * (pos.size + 1) / 2) / (pos.size * neg.size)


# ---------------------------------------------------------------------------
# Build (stratum × period) cells
# ---------------------------------------------------------------------------
def build_cells(df, strat_map, K=5):
    s = df["pid"].map(strat_map).to_numpy()
    tt = df["period"].to_numpy(dtype=int)
    expo = df["exposed"].to_numpy(dtype=float)
    out = df["outcome"].to_numpy(dtype=float)
    periods = sorted(int(v) for v in np.unique(tt))
    cells = {"g": [], "t": [], "N": [], "O": [], "p": []}
    for g in range(K):
        for tp in periods:
            m = (s == g) & (tt == tp)
            N = int(m.sum())
            if N == 0:
                continue
            cells["g"].append(g); cells["t"].append(tp)
            cells["N"].append(N)
            cells["O"].append(float(out[m].sum()))
            cells["p"].append(float(expo[m].mean()))
    for k in cells:
        cells[k] = np.array(cells[k], dtype=float)
    cells["periods"] = periods
    return cells


# ---------------------------------------------------------------------------
# Maximum-likelihood fit of the trend-in-trend marginal model
# ---------------------------------------------------------------------------
def _negloglik(params, cells, K):
    beta1, beta2 = params[0], params[1]
    alpha = params[2:2 + K]
    g = cells["g"].astype(int)
    q = np.exp(alpha[g] + beta2 * cells["t"]) * (1.0 + (np.exp(beta1) - 1.0) * cells["p"])
    q = np.clip(q, 1e-9, 1 - 1e-9)
    O, N = cells["O"], cells["N"]
    ll = O * np.log(q) + (N - O) * np.log(1 - q)
    return -float(np.sum(ll))


def _num_hessian(f, x, eps=1e-4):
    n = x.size
    H = np.zeros((n, n))
    fx = f(x)
    for i in range(n):
        for j in range(i, n):
            xi = x.copy(); xi[i] += eps; xi[j] += eps
            xj = x.copy(); xj[i] += eps; xj[j] -= eps
            xk = x.copy(); xk[i] -= eps; xk[j] += eps
            xl = x.copy(); xl[i] -= eps; xl[j] -= eps
            H[i, j] = H[j, i] = (f(xi) - f(xj) - f(xk) + f(xl)) / (4 * eps * eps)
    return H


def fit_tit(cells, K=5):
    base = np.log(max(cells["O"].sum() / cells["N"].sum(), 1e-4))
    x0 = np.concatenate([[0.0, 0.0], np.full(K, base)])
    res = optimize.minimize(_negloglik, x0, args=(cells, K), method="Nelder-Mead",
                            options={"maxiter": 4000, "xatol": 1e-7, "fatol": 1e-9})
    beta1 = float(res.x[0])
    # SE of beta1 from the inverse numerical Hessian of the negloglik
    try:
        H = _num_hessian(lambda p: _negloglik(p, cells, K), res.x)
        cov = np.linalg.pinv(H)
        se = float(np.sqrt(max(cov[0, 0], 0.0)))
    except Exception:
        se = float("nan")
    return beta1, se, res


def naive_or(df):
    e = df["exposed"].to_numpy(); o = df["outcome"].to_numpy()
    a = float(((e == 1) & (o == 1)).sum()); b = float(((e == 1) & (o == 0)).sum())
    c = float(((e == 0) & (o == 1)).sum()); d = float(((e == 0) & (o == 0)).sum())
    if b == 0 or c == 0:
        return float("nan")
    return (a * d) / (b * c)


# ---------------------------------------------------------------------------
# Trend plots: exposure & outcome prevalence by (stratum, period)
# ---------------------------------------------------------------------------
def trend_curves(cells, K=5):
    periods = cells["periods"]
    expo = {"periods": periods, "strata": []}
    outc = {"periods": periods, "strata": []}
    for g in range(K):
        ep, op = [], []
        for tp in periods:
            m = (cells["g"] == g) & (cells["t"] == tp)
            if m.any():
                ep.append(float(cells["p"][m][0]))
                op.append(float(cells["O"][m][0] / cells["N"][m][0]))
            else:
                ep.append(None); op.append(None)
        expo["strata"].append({"g": g, "p": ep})
        outc["strata"].append({"g": g, "q": op})
    return expo, outc


# ---------------------------------------------------------------------------
# High-level TiT analysis used by the API
# ---------------------------------------------------------------------------
def full_tit(df, covariates=("x1", "x2"), K=5, lang="zh"):
    strat_map, auc = cpe_strata(df, list(covariates), K=K)
    cells = build_cells(df, strat_map, K=K)
    beta1, se, res = fit_tit(cells, K=K)
    or_hat = float(np.exp(beta1))
    lo = float(np.exp(beta1 - 1.96 * se)) if np.isfinite(se) else None
    hi = float(np.exp(beta1 + 1.96 * se)) if np.isfinite(se) else None
    nv = naive_or(df)
    expo_curve, outc_curve = trend_curves(cells, K=K)
    out_rate = float(df["outcome"].mean())
    expo_overall = [float(cells["p"][cells["t"] == tp].mean()) for tp in cells["periods"]]
    expo_slope = float(expo_overall[-1] - expo_overall[0])

    interpretation = t(
        lang,
        f"趨勢中的趨勢（trend-in-trend）估計因果勝算比 OR ≈ {or_hat:.2f}"
        + (f"（95% 信賴區間 {lo:.2f}～{hi:.2f}）" if lo else "")
        + f"。對照：直接比較用藥與未用藥的天真世代勝算比約 {nv:.2f}，被未測混淆（體質／就醫傾向）高估。"
        f"整體結果發生率 {out_rate*100:.1f}%（夠罕見），暴露盛行率在觀察期內從 {expo_overall[0]*100:.0f}% "
        f"升到 {expo_overall[-1]*100:.0f}%（有足夠的時間趨勢可用）。",
        f"The trend-in-trend estimate of the causal odds ratio is OR ≈ {or_hat:.2f}"
        + (f" (95% CI {lo:.2f}–{hi:.2f})" if lo else "")
        + f". Contrast: the naive cohort odds ratio comparing users vs non-users is about {nv:.2f}, "
        f"inflated by unmeasured confounding. The overall outcome rate is {out_rate*100:.1f}% (rare enough), "
        f"and exposure prevalence rises from {expo_overall[0]*100:.0f}% to {expo_overall[-1]*100:.0f}% "
        f"over the window (a usable time trend).",
    )

    return {
        "or": or_hat, "log_or_se": se if np.isfinite(se) else None,
        "ci": [lo, hi], "naive_or": nv,
        "beta1": beta1, "K": K, "cpe_auc": auc,
        "outcome_rate": out_rate,
        "exposure_overall": expo_overall, "exposure_slope": expo_slope,
        "exposure_curve": expo_curve, "outcome_curve": outc_curve,
        "n_people": int(df["pid"].nunique()), "n_periods": len(cells["periods"]),
        "interpretation": interpretation,
        "converged": bool(res.success),
    }

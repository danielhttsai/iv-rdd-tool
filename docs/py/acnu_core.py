"""Active-Comparator, New-User (ACNU) core — pure numpy.

白話：要問「新藥 A 會不會提高某結果的風險」，天真地拿<b>用 A 的人 vs 沒用藥的人</b>比會中兩種偏誤：
(1) <b>因適應症而生的混淆</b>——病情重的人才會被開 A；(2) <b>healthy-user</b>——沒用藥的人通常比較健康。
兩者都讓 A 看起來比實際更有害。

ACNU 的解法：只比<b>新使用者</b>，且用一個<b>主動對照藥 B</b>（同適應症、病人相似）當對照——
A 的新使用者 vs B 的新使用者。兩組都有這個病、都剛起始、時間零點明確，<b>因適應症的混淆與
healthy-user／immortal-time 偏誤大幅相消</b>。A 與 B 之間若還有殘留的嚴重度差，再用<b>傾向分數／
共變項校正</b>補掉，就能還原真實的速率比。

  naive IRR   = (事件_A / 人時_A) ÷ (事件_none / 人時_none)        天真：A vs 沒用藥（偏）
  ACNU crude  = (事件_A / 人時_A) ÷ (事件_B    / 人時_B)           限制在新使用者＋主動對照（較不偏）
  ACNU adj    = exp(β_A)  from a Poisson rate model on A∪B         再校正殘留嚴重度 → ≈ 真值
                (offset = log person-time, covariates = severity, comorbidity)

NOTE — faithful-but-simplified teaching reconstruction (Lund, Richardson & Stürmer 2015,
Curr Epidemiol Rep 2:221; Ray 2003, AJE 158:915; Yoshida, Solomon & Kim 2015, Nat Rev
Rheumatol 11:437). Synthetic data only; not a copy of any package.
"""
from __future__ import annotations

import numpy as np

from i18n import t


def _poisson_fit(X, y, offset, iters=60):
    """Poisson regression via IRLS. log(E[y]) = offset + X@beta. Returns beta, se."""
    beta = np.zeros(X.shape[1])
    for _ in range(iters):
        eta = offset + X @ beta
        mu = np.exp(np.clip(eta, -30, 30))
        W = mu + 1e-9
        grad = X.T @ (y - mu)
        H = (X * W[:, None]).T @ X + 1e-8 * np.eye(X.shape[1])
        step = np.linalg.solve(H, grad)
        beta = beta + step
        if np.max(np.abs(step)) < 1e-9:
            break
    eta = offset + X @ beta
    mu = np.exp(np.clip(eta, -30, 30))
    W = mu + 1e-9
    cov = np.linalg.inv((X * W[:, None]).T @ X + 1e-8 * np.eye(X.shape[1]))
    return beta, np.sqrt(np.diag(cov))


def _irr(event, fut, g1, g2):
    e1, t1 = float(event[g1].sum()), float(fut[g1].sum())
    e2, t2 = float(event[g2].sum()), float(fut[g2].sum())
    if t1 <= 0 or t2 <= 0 or e1 <= 0 or e2 <= 0:
        return float("nan"), [float("nan"), float("nan")]
    irr = (e1 / t1) / (e2 / t2)
    se = float(np.sqrt(1.0 / e1 + 1.0 / e2))                # delta method on log-rate-ratio
    return float(irr), [float(irr * np.exp(-1.96 * se)), float(irr * np.exp(1.96 * se))]


def full_acnu(df, drug="drug", event="event", futime="futime",
              covariates=("severity", "comorbidity"), true_hr=None, lang="zh"):
    import acnu_gen
    if true_hr is None:
        true_hr = acnu_gen.TRUE_HR
    g = np.asarray(df[drug])
    ev = np.asarray(df[event], dtype=float)
    fu = np.asarray(df[futime], dtype=float)
    isA, isB, isN = g == "A", g == "B", g == "none"

    naive, ci_naive = _irr(ev, fu, isA, isN)               # A vs non-user (biased)
    crude, ci_crude = _irr(ev, fu, isA, isB)               # A vs active comparator (less biased)

    # severity-adjusted ACNU: Poisson rate model on A∪B, offset = log(person-time)
    sel = isA | isB
    aflag = isA[sel].astype(float)
    cols = [aflag]
    for cov in covariates:
        if cov in df.columns:
            cols.append(np.asarray(df[cov], dtype=float)[sel])
    X = np.column_stack([np.ones(int(sel.sum()))] + cols)
    offset = np.log(np.clip(fu[sel], 1e-6, None))
    beta, se = _poisson_fit(X, ev[sel], offset)
    adj = float(np.exp(beta[1]))
    ci_adj = [float(np.exp(beta[1] - 1.96 * se[1])), float(np.exp(beta[1] + 1.96 * se[1]))]

    # severity balance (why naive is so biased; why crude ACNU still needs adjustment)
    sev = np.asarray(df["severity"], dtype=float) if "severity" in df.columns else None
    bal = None
    if sev is not None:
        bal = {"A": float(sev[isA].mean()), "B": float(sev[isB].mean()),
               "none": float(sev[isN].mean())}

    interp = t(
        lang,
        f"天真地比『用 A vs 沒用藥』得速率比 ≈ <b>{naive:.2f}</b>（95% CI {ci_naive[0]:.2f}～{ci_naive[1]:.2f}）"
        f"——嚴重看高。因為用 A 的人嚴重度平均 {bal['A']:+.2f}、沒用藥的只有 {bal['none']:+.2f}（healthy-user＋"
        f"因適應症的混淆）。改用 <b>ACNU</b>：A 的新使用者 vs <b>主動對照藥 B</b> 的新使用者，粗速率比降到 "
        f"≈ {crude:.2f}（兩組都有這病、嚴重度 {bal['A']:+.2f} vs {bal['B']:+.2f}，差距小很多）；再<b>校正嚴重度</b>"
        f"後 ≈ <b>{adj:.2f}</b>（95% CI {ci_adj[0]:.2f}～{ci_adj[1]:.2f}）——貼近真值 {true_hr:.2f}。"
        if bal else
        f"天真 IRR ≈ {naive:.2f}；ACNU 粗 ≈ {crude:.2f}；校正後 ≈ {adj:.2f}（真值 {true_hr:.2f}）。",
        f"Naively comparing 'A vs non-users' gives a rate ratio ≈ <b>{naive:.2f}</b> (95% CI {ci_naive[0]:.2f}–"
        f"{ci_naive[1]:.2f}) — badly inflated, because A users average severity {bal['A']:+.2f} vs {bal['none']:+.2f} for "
        f"non-users (healthy-user + confounding by indication). Switching to <b>ACNU</b> — new users of A vs new users of the "
        f"<b>active comparator B</b> — drops the crude rate ratio to ≈ {crude:.2f} (both indicated; severity {bal['A']:+.2f} "
        f"vs {bal['B']:+.2f}, a much smaller gap); <b>adjusting for severity</b> then gives ≈ <b>{adj:.2f}</b> (95% CI "
        f"{ci_adj[0]:.2f}–{ci_adj[1]:.2f}) — close to the truth {true_hr:.2f}."
        if bal else
        f"Naive IRR ≈ {naive:.2f}; crude ACNU ≈ {crude:.2f}; adjusted ≈ {adj:.2f} (truth {true_hr:.2f}).",
    )
    return {
        "naive_irr": float(naive), "ci_naive": ci_naive,
        "crude_irr": float(crude), "ci_crude": ci_crude,
        "adj_irr": adj, "ci_adj": ci_adj, "true_hr": float(true_hr),
        "severity_balance": bal,
        "n_a": int(isA.sum()), "n_b": int(isB.sum()), "n_none": int(isN.sum()),
        "events": {"A": int(ev[isA].sum()), "B": int(ev[isB].sum()), "none": int(ev[isN].sum())},
        "interpretation": interp,
    }


# ---------------------------------------------------------------------------
# ② interactive — confounding-by-indication knob. As severity drives the A-vs-B
# choice more strongly (conf↑), the naive 'A vs none' AND crude ACNU drift up,
# but the severity-adjusted ACNU stays on truth. Offline-precomputed grid.
# ---------------------------------------------------------------------------
_CONF_X = [0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5]


def _recompute_grid(n=120000):
    """Offline: recompute the ② grid (naive / crude ACNU / adjusted ACNU vs conf)."""
    import acnu_gen
    out = {"conf": _CONF_X, "naive": [], "crude": [], "adj": [], "true_hr": acnu_gen.TRUE_HR}
    for c in out["conf"]:
        df = acnu_gen.generate(seed=99, n=n, conf=c)
        r = full_acnu(df)
        out["naive"].append(round(r["naive_irr"], 3))
        out["crude"].append(round(r["crude_irr"], 3))
        out["adj"].append(round(r["adj_irr"], 3))
    return out


# precomputed grid via _recompute_grid(n=120000) — naive stays biased; crude ACNU drifts
# up with confounding; severity-adjusted ACNU holds the truth.
_GRID = {
    "conf": [0.0, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5],
    "naive": [3.171, 3.490, 3.740, 3.913, 4.030, 4.114, 4.176],
    "crude": [1.482, 1.838, 2.233, 2.614, 2.963, 3.271, 3.581],
    "adj": [1.570, 1.578, 1.586, 1.578, 1.560, 1.555, 1.561],
    "true_hr": 1.6,
}


def acnu_interactive(conf=1.0, lang="zh"):
    g = _GRID
    xc = float(np.clip(conf, g["conf"][0], g["conf"][-1]))
    naive = float(np.interp(xc, g["conf"], g["naive"]))
    crude = float(np.interp(xc, g["conf"], g["crude"]))
    adj = float(np.interp(xc, g["conf"], g["adj"]))
    reading = t(
        lang,
        f"因適應症的混淆強度 {xc:.2f}（嚴重度左右『拿 A 還是 B』的程度）：天真『A vs 沒用藥』≈ {naive:.2f}、"
        f"ACNU 粗『A vs B』≈ {crude:.2f}，都被嚴重度推離真值；<b>校正嚴重度後的 ACNU ≈ {adj:.2f}</b>，"
        f"穩定停在真值 {g['true_hr']:.1f}。注意：主動對照（A vs B）一開始就比『A vs 沒用藥』少偏很多——"
        f"因為兩組都有這個病；剩下的殘留混淆再靠校正補掉。",
        f"Confounding-by-indication strength {xc:.2f} (how strongly severity drives A-vs-B): the naive 'A vs non-users' "
        f"≈ {naive:.2f} and crude ACNU 'A vs B' ≈ {crude:.2f} are both pushed off by severity; the "
        f"<b>severity-adjusted ACNU ≈ {adj:.2f}</b> stays on the truth {g['true_hr']:.1f}. Note the active comparator "
        f"(A vs B) starts far less biased than 'A vs non-users' because both groups are indicated; the residual confounding "
        f"is then mopped up by adjustment.",
    )
    return {"conf": xc, "naive_irr": naive, "crude_irr": crude, "adj_irr": adj,
            "true_hr": g["true_hr"], "grid": g, "reading": reading}

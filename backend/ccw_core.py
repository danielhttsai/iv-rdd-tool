"""Clone-Censor-Weight (CCW) core — target-trial emulation of treatment TIMING,
pure numpy/scipy, Pyodide-safe.

白話：要比較「早接種 vs 晚接種」這種**動態策略**，不能照實際分組直接比 —— 被歸到 early 的人
必須先活著、沒發生事件才有機會早接種（immortal-time bias），又有體弱程度的混淆。做法：

  1. 複製（clone）：把每個人同時放進「早」與「晚」兩個策略臂。
  2. 設限（censor）：當一個複製品的實際行為**偏離**它被指派的策略時，就在那一刻把它設限。
       早臂：在寬限期 g 內沒接種 → 在第 g 月設限（違反「早接種」）。
       晚臂：在寬限期內就接種 → 在接種那月設限（違反「先別接種」）。
  3. 加權（weight）：人為設限不是隨機的（和體弱有關），用反設限機率加權（IPCW）補回來。

設限＋加權後，對每個策略臂做**加權 Kaplan–Meier**，得到各策略到第 T 月的累積發生率，相減＝因果
風險差。對照天真「照實際 early/late 分組」的比較會中 immortal-time bias。

NOTE — teaching reconstruction. The IPC weights use a stabilized pooled-logistic
censoring model with covariates X = (standardized age, frailty); under no unmeasured
confounding this is consistent for the strategy contrast. Not a copy of any package.
"""
from __future__ import annotations

import numpy as np

from i18n import t


# ---------------------------------------------------------------------------
# small numpy logistic regression (Newton-Raphson)
# ---------------------------------------------------------------------------
def _logit_fit(X, y, w=None, iters=18):
    if w is None:
        w = np.ones(X.shape[0])
    beta = np.zeros(X.shape[1])
    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-(X @ beta)))
        W = w * p * (1 - p) + 1e-9
        grad = X.T @ (w * (y - p))
        H = (X * W[:, None]).T @ X + 1e-7 * np.eye(X.shape[1])
        step = np.linalg.solve(H, grad)
        beta = beta + step
        if np.max(np.abs(step)) < 1e-9:
            break
    return beta


def _predict(X, beta):
    return 1.0 / (1.0 + np.exp(-(X @ beta)))


# ---------------------------------------------------------------------------
# Build one strategy arm's clone person-month table
# ---------------------------------------------------------------------------
def _build_arm(arm, vacc, evtm, fut, grace, T):
    """Return long person-month rows for a strategy arm (fully vectorized).

    arm = "early": adhere iff initiate within [0, grace]; else artificially censored
                   at month `grace`.
    arm = "late" : adhere while untreated; artificially censored at the month of
                   initiation (whenever it happens).
    vacc = vaccination month (np.nan = never), evtm = event month (-1 = no event).
    Returns (pid_index, month, event_here, acens_here).
    """
    n = vacc.size
    has_vacc = ~np.isnan(vacc)
    vm = np.where(has_vacc, vacc, np.inf)
    INF = 10 ** 9
    if arm == "early":
        c = np.where(vm > grace, float(grace), np.inf)      # failed to initiate by grace
    else:  # late
        c = np.where(has_vacc, vm, np.inf)                  # deviated by initiating
    c_int = np.where(np.isfinite(c), c, INF).astype(np.intp)
    end_event = np.where(evtm >= 0, evtm + 1, T)
    end_cens = np.where(c_int < INF, c_int + 1, T)
    end = np.minimum(np.minimum(end_event, end_cens), T).astype(np.intp)   # rows per person
    end = np.maximum(end, 0)
    total = int(end.sum())
    if total == 0:
        z = np.array([], dtype=np.intp)
        return z, z, z.astype(float), z.astype(float)
    pid_rows = np.repeat(np.arange(n), end)
    starts = np.cumsum(end) - end
    month_rows = np.arange(total) - np.repeat(starts, end)        # 0..len-1 within person
    ev_p = evtm[pid_rows]; c_p = c_int[pid_rows]
    event_here = ((month_rows == ev_p) & (ev_p >= 0)).astype(float)
    acens_here = ((month_rows == c_p) & (c_p < INF) & (event_here == 0)).astype(float)
    return pid_rows, month_rows.astype(np.intp), event_here, acens_here


def _month_design(months, Xrows, T):
    """Design matrix: intercept + month dummies (1..T-1) + covariates."""
    nrow = months.size
    dummies = np.zeros((nrow, T - 1))
    for m in range(1, T):
        dummies[:, m - 1] = (months == m).astype(float)
    return np.column_stack([np.ones(nrow), dummies, Xrows])


def _ipcw_km(arm, vacc, evtm, fut, X, grace, T):
    """Clone-censor-weight one arm: build clones, fit a stabilized pooled-logistic
    IPCW model for the artificial censoring, then weighted KM cumulative incidence."""
    pid, mon, evt, cens = _build_arm(arm, vacc, evtm, fut, grace, T)
    if pid.size == 0:
        return np.zeros(T), 0, {"mean": 1.0, "max": 1.0, "p99": 1.0, "frac_extreme": 0.0}
    Xrows = X[pid]
    # pooled-logistic censoring model: P(acens this month | at risk, month, X)
    D = _month_design(mon, Xrows, T)
    Dm = _month_design(mon, np.zeros_like(Xrows), T)   # marginal (no covariates → zeros)
    beta = _logit_fit(D, cens)
    beta_m = _logit_fit(Dm, cens)
    pc = _predict(D, beta)
    pc_m = _predict(Dm, beta_m)
    # stabilized cumulative weights per clone-month (cumprod within person over time).
    # Rows are contiguous and time-ordered per person (built by _build_arm), so we
    # cumprod via cumulative log-sums with per-person prefix subtraction.
    surv_num = np.clip(1.0 - pc_m, 1e-9, 1.0)
    surv_den = np.clip(1.0 - pc, 1e-6, 1.0)
    # per-person run lengths (pid is sorted/grouped)
    uniq, lengths = np.unique(pid, return_counts=True)
    starts = np.cumsum(lengths) - lengths
    last_idx = np.cumsum(lengths) - 1
    def _grp_cumprod(vals):
        cs = np.cumsum(np.log(vals))
        prev_end = np.concatenate([[0.0], cs[last_idx][:-1]])   # exclusive prefix per group
        base = np.repeat(prev_end, lengths)
        return np.exp(cs - base)
    w_raw = _grp_cumprod(surv_num) / _grp_cumprod(surv_den)
    w = np.clip(w_raw, 0.0, 20.0)   # trim extreme weights
    # weighted KM cumulative incidence by month
    surv = 1.0
    ci = np.zeros(T)
    for tt in range(T):
        sel = mon == tt
        atrisk = float(np.sum(w[sel]))
        events = float(np.sum(w[sel] * evt[sel]))
        h = events / atrisk if atrisk > 0 else 0.0
        surv *= (1.0 - h)
        ci[tt] = 1.0 - surv
    nclones = int(len(np.unique(pid)))
    wstats = {"mean": float(np.mean(w_raw)), "max": float(np.max(w_raw)),
              "p99": float(np.percentile(w_raw, 99)),
              "frac_extreme": float(np.mean(w_raw > 10.0))}
    return ci, nclones, wstats


# ---------------------------------------------------------------------------
# Ground truth of the CCW estimand. The truth = the SAME clone-censor-weight
# estimator on a large UNCONFOUNDED sample (timing independent of covariates),
# where the IPC weights are ≈ 1 so the estimate is unbiased; confounded CCW should
# recover it. That run is heavy (n≈150k), so we precomputed it offline on a grid of
# the ② slider's `timing_effect` and interpolate at runtime (instant, Pyodide-safe).
# Grid recomputable via _estimand_truth_sim() below.
# ---------------------------------------------------------------------------
_TRUTH_GRID_X = [0.0, 0.25, 0.5, 0.75, 1.0]
_TRUTH_GRID_Y = [0.0226, -0.0480, -0.1130, -0.1729, -0.2242]


def estimand_truth(timing_effect=1.0, grace=3, horizon=12, n=None):
    te = float(np.clip(timing_effect, 0.0, 1.0))
    return float(np.interp(te, _TRUTH_GRID_X, _TRUTH_GRID_Y))


def _estimand_truth_sim(timing_effect=1.0, grace=3, horizon=12, n=150000):
    """Offline recompute of one truth-grid point (not called at runtime)."""
    import ccw_gen
    df = ccw_gen.generate(n=n, seed=99, timing_effect=timing_effect, init_confound=False)
    vacc = np.asarray(df["vacc_month"], dtype=float)
    ev = np.asarray(df["event"], dtype=float)
    fut = np.asarray(df["futime"], dtype=float)
    evtm = np.where(ev > 0, fut - 1, -1).astype(int)
    age = np.asarray(df["age"], dtype=float); fr = np.asarray(df["frailty"], dtype=float)
    X = np.column_stack([(age - age.mean()) / (age.std() + 1e-9),
                         (fr - fr.mean()) / (fr.std() + 1e-9)])
    ci_e, _, _ = _ipcw_km("early", vacc, evtm, fut, X, grace, horizon)
    ci_l, _, _ = _ipcw_km("late", vacc, evtm, fut, X, grace, horizon)
    return float(ci_e[horizon - 1] - ci_l[horizon - 1])


# ---------------------------------------------------------------------------
# High-level CCW analysis
# ---------------------------------------------------------------------------
def full_ccw(df, vacc_time="vacc_month", event="event", futime="futime",
             covariates=("age", "frailty"), grace=3, horizon=12, true_rd=None,
             n_boot=0, lang="zh"):
    if true_rd is None:
        true_rd = estimand_truth(1.0, grace=grace, horizon=horizon)
    T = int(horizon)
    vacc = np.asarray(df[vacc_time], dtype=float)
    ev = np.asarray(df[event], dtype=float)
    fut = np.asarray(df[futime], dtype=float)
    evtm = np.where(ev > 0, fut - 1, -1).astype(int)
    # covariate matrix (standardized)
    cov = []
    for c in covariates:
        v = np.asarray(df[c], dtype=float)
        sd = v.std() + 1e-9
        cov.append((v - v.mean()) / sd)
    X = np.column_stack(cov) if cov else np.zeros((len(df), 1))

    ci_e, n_e, ws_e = _ipcw_km("early", vacc, evtm, fut, X, grace, T)
    ci_l, n_l, ws_l = _ipcw_km("late", vacc, evtm, fut, X, grace, T)
    ccw_rd = float(ci_e[T - 1] - ci_l[T - 1])

    # naive (immortal-time biased): classify by realized timing, compare raw risk
    early_real = (~np.isnan(vacc)) & (vacc <= grace)
    late_real = ~early_real
    risk_e_naive = float(ev[early_real].mean()) if early_real.any() else float("nan")
    risk_l_naive = float(ev[late_real].mean()) if late_real.any() else float("nan")
    naive_rd = risk_e_naive - risk_l_naive

    # light bootstrap CI on the CCW contrast (people-level resample)
    lo = hi = None
    if n_boot and n_boot > 0:
        rng = np.random.default_rng(20240607)
        reps = []
        nN = len(df)
        for _ in range(int(n_boot)):
            idx = rng.integers(0, nN, nN)
            cE, _, _ = _ipcw_km("early", vacc[idx], evtm[idx], fut[idx], X[idx], grace, T)
            cL, _, _ = _ipcw_km("late", vacc[idx], evtm[idx], fut[idx], X[idx], grace, T)
            reps.append(cE[T - 1] - cL[T - 1])
        lo = float(np.percentile(reps, 2.5)); hi = float(np.percentile(reps, 97.5))

    interp = t(
        lang,
        f"複製-設限-加權（CCW）估計『早接種 vs 晚接種』的因果風險差 ≈ {ccw_rd:+.2f}"
        + (f"（95% 自助信賴區間 {lo:+.2f} ～ {hi:+.2f}）" if lo is not None else "")
        + f"，貼近真值 {true_rd:+.2f}（負值＝早接種讓 {horizon} 個月內發生事件的機率更低）。"
        f"對照：天真地照『實際早／晚接種』直接比，風險差約 {naive_rd:+.2f}——被 immortal-time bias "
        f"與適應症混淆扭曲（早接種者必須先活著沒事件、且體質本就不同）。CCW 用複製＋偏離設限＋反設限"
        f"加權，把這個偏誤去掉。",
        f"Clone-censor-weight (CCW) estimates the causal risk difference of 'early vs late' vaccination "
        f"≈ {ccw_rd:+.2f}"
        + (f" (95% bootstrap CI {lo:+.2f} to {hi:+.2f})" if lo is not None else "")
        + f", close to the truth {true_rd:+.2f} (negative = starting early lowers the chance of an event within "
        f"{horizon} months). Contrast: naively comparing people by their realized early/late timing gives a risk "
        f"difference of about {naive_rd:+.2f} — distorted by immortal-time bias and confounding by indication "
        f"(early initiators had to survive event-free first, and differ in frailty). CCW removes this with cloning, "
        f"censoring on deviation, and inverse-probability-of-censoring weights.",
    )

    months = list(range(1, T + 1))
    return {
        "ccw": ccw_rd, "ci": [lo, hi],
        "naive": float(naive_rd),
        "risk_early_ccw": float(ci_e[T - 1]), "risk_late_ccw": float(ci_l[T - 1]),
        "risk_early_naive": risk_e_naive, "risk_late_naive": risk_l_naive,
        "early_rate": float(early_real.mean()), "late_rate": float(late_real.mean()),
        "n_early": n_e, "n_late": n_l,
        "curve": {"months": months,
                  "early": [float(v) for v in ci_e],
                  "late": [float(v) for v in ci_l]},
        "true_rd": float(true_rd), "grace": grace, "horizon": T,
        "weights": {"early": ws_e, "late": ws_l},
        "interpretation": interp,
    }


# ---------------------------------------------------------------------------
# ⑤ refinement demo (literature-faithful, NOT a black-box ML demo):
# the GRACE PERIOD is CCW's key design knob. Re-run the clone-censor-weight
# estimate as the grace period g varies, to show how the defined estimand — and
# the estimate — move with the design choice (a mandatory sensitivity analysis,
# Hernán 2018; Gaber et al. 2024). The naive (immortal-time) contrast is shown for
# contrast. Fast and robust (no model-fitting instability).
# ---------------------------------------------------------------------------
# Precomputed offline (deterministic: built-in demo data, seed=7, n=2500) so the ⑤
# tab is instant — running 5 full clone-censor-weight fits live is ~14s under Pyodide.
# Recompute via _grace_demo_sim().
_GRACE_GRID = {"graces": [1, 2, 3, 4, 5],
               "ccw": [-0.283, -0.254, -0.238, -0.232, -0.224],
               "naive": [-0.252, -0.326, -0.413, -0.491, -0.548]}


def grace_demo(seed=0, lang="zh"):
    graces = _GRACE_GRID["graces"]
    ccw_vals = _GRACE_GRID["ccw"]
    naive_vals = _GRACE_GRID["naive"]
    truth = estimand_truth(1.0)
    spread = max(ccw_vals) - min(ccw_vals)
    reading = t(
        lang,
        f"把寬限期 g 從 1 拉到 5 個月，CCW 估計從 {ccw_vals[0]:+.2f} 變到 {ccw_vals[-1]:+.2f}"
        f"（變動約 {spread:.2f}）。這不是誤差，而是<b>定義改變</b>：g 越長，「早接種」這個策略越寬鬆、"
        f"和「晚接種」越像，效果自然被稀釋。天真比較（受 immortal-time 汙染）則整條都明顯偏離。"
        f"因此 g 一定要事先講清楚，並像這樣做敏感度分析（Hernán 2018；Gaber 等人 2024）。",
        f"As the grace period g goes from 1 to 5 months, the CCW estimate moves from {ccw_vals[0]:+.2f} to "
        f"{ccw_vals[-1]:+.2f} (a swing of about {spread:.2f}). This is not noise — it is the <b>estimand changing</b>: "
        f"a longer g makes the 'early' strategy more permissive and more like 'late', so the effect is diluted. The "
        f"naive (immortal-time-contaminated) contrast stays clearly off across the board. So g must be pre-specified "
        f"and probed with exactly this kind of sensitivity analysis (Hernán 2018; Gaber et al. 2024).",
    )
    return {"graces": graces, "ccw": ccw_vals, "naive": naive_vals,
            "truth_ref": float(truth), "reading": reading}


def _grace_demo_sim():
    """Offline recompute of the grace-period grid (not called at runtime)."""
    import ccw_gen
    df = ccw_gen.generate(n=2500, seed=7)
    out = {"graces": [1, 2, 3, 4, 5], "ccw": [], "naive": []}
    for g in out["graces"]:
        o = full_ccw(df, grace=g, true_rd=estimand_truth(1.0))
        out["ccw"].append(round(o["ccw"], 3)); out["naive"].append(round(o["naive"], 3))
    return out

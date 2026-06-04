"""Sequential (nested) trials core — emulate one target trial per eligibility month,
align time-zero, pool. Pure numpy, Pyodide-safe.

白話：點治療「當下治療 vs 不治療」。病人在不同月份陸續符合資格 → 每個資格月 k 開一場 mini-trial：
時間零點＝月 k，比較「當月啟動 vs 當月不啟動」的合格者，用基線共變項做傾向＋反機率加權（IPTW），
得到該場的風險差 RD_k；再以反變異把各場合併。同一個人可在多場以「未啟動」身分重複納入（放大有效
樣本）。對照天真「曾治療 vs 從未治療」會中 immortal-time bias。

  RD_k    = riskW(該月啟動者) − riskW(該月未啟動者)，到 horizon 的事件風險
  RD_pool = Σ_k (RD_k / Var_k) / Σ_k (1/Var_k)     （反變異合併）
  SE_pool ：因重複收案，用個人叢集自助（重抽 pid）較誠實。

NOTE — faithful-but-simplified teaching reconstruction (Hernán & Robins target-trial;
Danaei et al. nested sequential trials; Gran et al.). The literature stacks
Cox/pooled-logistic with person-robust SEs; here we use per-trial IPTW + inverse-
variance pooling + a person-cluster bootstrap SE. Not a copy of any package.
"""
from __future__ import annotations

import numpy as np

from i18n import t


def _logit_fit(X, y, iters=18):
    beta = np.zeros(X.shape[1])
    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-(X @ beta)))
        W = p * (1 - p) + 1e-9
        g = X.T @ (y - p)
        H = (X * W[:, None]).T @ X + 1e-7 * np.eye(X.shape[1])
        step = np.linalg.solve(H, g)
        beta = beta + step
        if np.max(np.abs(step)) < 1e-9:
            break
    return beta


def _predict(X, beta):
    return 1.0 / (1.0 + np.exp(-(X @ beta)))


def _nested(init, evtm, ev, X, n_trials, horizon, T):
    """Run the nested trials; return (rds, vars, per_trial)."""
    rds, vars_, per = [], [], []
    for k in range(n_trials):
        eligible = (evtm < 0) | (evtm >= k)          # event-free at start of month k
        untreated = np.isnan(init) | (init >= k)     # untreated at start of month k
        elig = eligible & untreated
        if elig.sum() < 40:
            continue
        A = ((~np.isnan(init)) & (init == k))[elig].astype(float)   # initiate at k
        if A.sum() < 10 or (1 - A).sum() < 10:
            continue
        Y = (ev[elig] > 0).astype(float)             # event by end of follow-up
        Xk = X[elig]
        Xd = np.column_stack([np.ones(Xk.shape[0]), Xk])
        e = np.clip(_predict(Xd, _logit_fit(Xd, A)), 0.02, 0.98)
        w = np.where(A == 1, 1.0 / e, 1.0 / (1.0 - e))
        rT = float(np.sum(w[A == 1] * Y[A == 1]) / np.sum(w[A == 1]))
        rN = float(np.sum(w[A == 0] * Y[A == 0]) / np.sum(w[A == 0]))
        nT = float(A.sum()); nN = float((1 - A).sum())
        var = rT * (1 - rT) / max(nT, 1) + rN * (1 - rN) / max(nN, 1)
        rds.append(rT - rN); vars_.append(max(var, 1e-6))
        per.append({"k": k, "rd": float(rT - rN), "n_init": int(nT), "n_non": int(nN)})
    return np.array(rds), np.array(vars_), per


def _pool(rds, vars_):
    if rds.size == 0:
        return float("nan")
    return float(np.sum(rds / vars_) / np.sum(1.0 / vars_))


# ---------------------------------------------------------------------------
# Ground truth: the SAME nested estimator on UNCONFOUNDED data (conf=0 → IPTW
# weights ≈ 1 → unbiased). Precomputed offline over timing_effect; interpolated.
# ---------------------------------------------------------------------------
_TRUTH_X = [0.0, 0.25, 0.5, 0.75, 1.0]
_TRUTH_Y = [-0.0383, -0.0884, -0.1421, -0.1911, -0.2339]   # offline (estimator on conf=0 data)


def estimand_truth(timing_effect=1.0):
    return float(np.interp(float(np.clip(timing_effect, 0.0, 1.0)), _TRUTH_X, _TRUTH_Y))


def _truth_sim(timing_effect=1.0, n=120000):
    import seq_gen
    df = seq_gen.generate(n=n, seed=99, timing_effect=timing_effect, conf=0.0)
    return _from_df(df)["seq_rd"]


def _from_df(df, n_trials=None, horizon=None):
    import seq_gen
    n_trials = seq_gen.N_TRIALS if n_trials is None else n_trials
    horizon = seq_gen.HORIZON if horizon is None else horizon
    init = np.asarray(df["init_month"], dtype=float)
    ev = np.asarray(df["event"], dtype=float)
    fut = np.asarray(df["futime"], dtype=float)
    evtm = np.where(ev > 0, fut - 1, -1).astype(np.intp)
    age = np.asarray(df["age"], dtype=float); fr = np.asarray(df["frailty"], dtype=float)
    X = np.column_stack([(age - age.mean()) / (age.std() + 1e-9),
                         (fr - fr.mean()) / (fr.std() + 1e-9)])
    rds, vars_, per = _nested(init, evtm, ev, X, n_trials, horizon, seq_gen.T)
    seq_rd = _pool(rds, vars_)
    se = float(np.sqrt(1.0 / np.sum(1.0 / vars_))) if rds.size else float("nan")
    return {"seq_rd": seq_rd, "se": se, "per_trial": per, "init": init, "ev": ev}


def full_seq(df, init_time="init_month", event="event", futime="futime",
             covariates=("age", "frailty"), n_trials=None, horizon=None,
             true_rd=None, n_boot=0, lang="zh"):
    import seq_gen
    if true_rd is None:
        true_rd = estimand_truth(1.0)
    out = _from_df(df, n_trials, horizon)
    seq_rd, se, per = out["seq_rd"], out["se"], out["per_trial"]
    init = out["init"]; ev = out["ev"]
    # naive: ever-treated vs never-treated (immortal-time biased)
    ever = ~np.isnan(init); never = ~ever
    naive_rd = float(ev[ever].mean() - ev[never].mean())
    lo = float(seq_rd - 1.96 * se); hi = float(seq_rd + 1.96 * se)

    # optional person-cluster bootstrap CI (heavier; default off)
    if n_boot and n_boot > 0:
        rng = np.random.default_rng(20240608); reps = []; nN = len(df)
        for _ in range(int(n_boot)):
            idx = rng.integers(0, nN, nN)
            reps.append(_from_df(df.iloc[idx])["seq_rd"])
        lo = float(np.percentile(reps, 2.5)); hi = float(np.percentile(reps, 97.5))

    interp = t(
        lang,
        f"序列（巢式）試驗合併估計『當下治療 vs 不治療』的因果風險差 ≈ {seq_rd:+.2f}"
        f"（95% 區間 {lo:+.2f} ～ {hi:+.2f}），貼近真值 {true_rd:+.2f}（負值＝治療讓事件風險更低）。"
        f"做法：在 {len(per)} 個資格月各開一場 mini-trial、對齊時間零點、用基線共變項 IPTW，再反變異合併。"
        f"對照：天真比『曾治療 vs 從未治療』約 {naive_rd:+.2f}——被 immortal-time bias 與混淆扭曲"
        f"（曾治療者必須先活著、撐到治療那刻）。",
        f"Sequential (nested) trials pool an estimate of the 'treat-now vs not' causal risk difference ≈ {seq_rd:+.2f} "
        f"(95% interval {lo:+.2f} to {hi:+.2f}), close to the truth {true_rd:+.2f} (negative = treatment lowers the "
        f"event risk). Recipe: open a mini-trial at each of {len(per)} eligibility months, align time-zero, apply "
        f"baseline-covariate IPTW, then inverse-variance pool. Contrast: naively comparing 'ever- vs never-treated' "
        f"gives ≈ {naive_rd:+.2f} — distorted by immortal-time bias and confounding (ever-treated had to survive to "
        f"their treatment month).",
    )
    return {
        "seq_rd": seq_rd, "ci": [lo, hi], "naive": naive_rd, "true_rd": float(true_rd),
        "per_trial": per, "n_trials": len(per), "interpretation": interp,
    }


# ---------------------------------------------------------------------------
# ⑤ refinement demo — single baseline trial vs full sequential pooling. Using only
# the month-0 trial throws away later-eligible people (and is more immortal-time
# prone); pooling all nested trials uses everyone. Precomputed offline.
# ---------------------------------------------------------------------------
_SEQ_DEMO = {"naive": -0.69, "single": -0.23, "pooled": -0.22, "true_rd": -0.23}


def seq_demo(seed=0, lang="zh"):
    d = _SEQ_DEMO
    reading = t(
        lang,
        f"真值 {d['true_rd']:+.2f}。天真『曾 vs 從未治療』{d['naive']:+.2f}——嚴重中 immortal-time bias（曾治療者必須"
        f"先活著、撐到治療那刻，於是治療看起來假性超級保護）。只用『第 0 月那一場 trial』{d['single']:+.2f}：已經無偏，"
        f"但只用得到第 0 月的合格者、有效樣本小、區間較寬。<b>合併所有巢式 trial</b> {d['pooled']:+.2f}：用到每個資格"
        f"時點的人（同一人可重複收案）→ 更有效率、區間更窄，同樣貼近真值。",
        f"Truth {d['true_rd']:+.2f}. Naive 'ever vs never treated' {d['naive']:+.2f} — badly immortal-time biased "
        f"(ever-treated had to survive to their treatment month, so treatment looks spuriously protective). Using only "
        f"the month-0 trial {d['single']:+.2f} is already unbiased, but uses only month-0 eligibles, so the effective "
        f"sample is small and the interval wide. <b>Pooling all nested trials</b> {d['pooled']:+.2f} uses people at "
        f"every eligibility time (a person can re-enter) → more efficient, a tighter interval, equally on target.",
    )
    return {**d, "reading": reading}


def _seq_demo_sim(seed=57):
    import seq_gen
    df = seq_gen.generate(seed=seed)
    full = full_seq(df)
    single = full_seq(df, n_trials=1)
    return {"naive": round(full["naive"], 2), "single": round(single["seq_rd"], 2),
            "pooled": round(full["seq_rd"], 2), "true_rd": round(full["true_rd"], 2)}

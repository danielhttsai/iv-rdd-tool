"""DiD ⑤『用 AI／進階方法強化』—— 四個輕量教學 demo（小 N、固定種子）。

每個 demo 都鋪一個「天真 DiD 會在這裡出錯 → 進階方法把它救回來」的故事，回傳
比較數字＋一點點圖資料＋雙語白話。全部用 numpy/scipy 從頭實作，可在 Pyodide 跑。

對應四篇/四類文獻：
  dr        雙重穩健／DML DiD（共變項在兩組分布不同 → 條件平行趨勢）Sant'Anna–Zhao；Chang 2020 (utaa001)
  staggered 交錯採用（各單位不同時間受處置，TWFE 會偏）Callaway–Sant'Anna 2021；Goodman-Bacon 2021
  universal Universal DiD（二元結果，加法平行趨勢失效，改用勝算比）Tchetgen Tchetgen 2024
  synth     合成控制／合成 DiD（少數受處置單位，用控制組加權擬合反事實）Abadie 2010；Arkhangelsky 2021
"""
from __future__ import annotations

import numpy as np
from scipy import optimize

from i18n import t


# ---------------------------------------------------------------------------
# small numpy logistic regression (Newton-Raphson) — for propensity scores
# ---------------------------------------------------------------------------
def _logit_fit(X, y, iters=25):
    beta = np.zeros(X.shape[1])
    for _ in range(iters):
        eta = X @ beta
        p = 1.0 / (1.0 + np.exp(-eta))
        W = p * (1 - p) + 1e-9
        grad = X.T @ (y - p)
        H = (X * W[:, None]).T @ X
        step = np.linalg.solve(H + 1e-8 * np.eye(X.shape[1]), grad)
        beta = beta + step
        if np.max(np.abs(step)) < 1e-8:
            break
    return beta


def _ols(X, y):
    return np.linalg.pinv(X.T @ X) @ (X.T @ y)


# ===========================================================================
# 1) Doubly-robust / DML DiD — covariates differ between the two groups
# ===========================================================================
def _dr_did_crossfit(dY, treated, X, ps_model_factory, out_model_factory, rng, folds=2):
    """Sant'Anna–Zhao doubly-robust DiD with K-fold cross-fitting (nuisances
    predicted out-of-fold). ps_model_factory / out_model_factory return fresh
    sklearn-style estimators each call — so this works with linear OR ML nuisances."""
    n = len(dY)
    idx = rng.permutation(n)
    parts = np.array_split(idx, folds)
    m0 = np.zeros(n)
    e = np.zeros(n)
    for k in range(folds):
        te = parts[k]
        tr = np.concatenate([parts[j] for j in range(folds) if j != k])
        ctrl = tr[treated[tr] == 0]
        om = out_model_factory(); om.fit(X[ctrl], dY[ctrl]); m0[te] = om.predict(X[te])
        pm = ps_model_factory(); pm.fit(X[tr], treated[tr])
        e[te] = np.clip(pm.predict_proba(X[te])[:, 1], 0.02, 0.98)
    w1 = treated / treated.mean()
    w0 = (1 - treated) * e / (1 - e)
    w0 = w0 / w0.mean()
    return float(np.mean(w1 * (dY - m0)) - np.mean(w0 * (dY - m0)))


def dml_demo(seed=7, lang="zh"):
    """⑤ DiD — a GENUINE machine-learning estimator: double/debiased ML DiD with
    gradient-boosted nuisance models and cross-fitting. The confounding here is
    NONLINEAR in several covariates, so a linear doubly-robust version is still
    biased, while the ML version recovers the truth."""
    from sklearn.ensemble import GradientBoostingClassifier, GradientBoostingRegressor
    from sklearn.linear_model import LinearRegression, LogisticRegression
    rng = np.random.default_rng(seed)
    n = 1600
    true_att = 3.0
    X = rng.normal(0, 1, (n, 4))
    # NONLINEAR propensity & trend in the covariates -> linear models are misspecified
    g = 1.4 * np.sin(1.5 * X[:, 0]) + 0.9 * X[:, 1] ** 2 - 1.1 * X[:, 2] + 0.5 * X[:, 0] * X[:, 1]
    ps_true = 1.0 / (1.0 + np.exp(-(g - g.mean())))
    treated = rng.binomial(1, ps_true)
    dY = (1.0 + 2.2 * np.sin(1.5 * X[:, 0]) + 1.1 * X[:, 1] ** 2 + 0.7 * X[:, 2]
          + 0.6 * X[:, 0] * X[:, 1] + true_att * treated + rng.normal(0, 1.0, n))

    naive = float(dY[treated == 1].mean() - dY[treated == 0].mean())
    lin = _dr_did_crossfit(
        dY, treated, X,
        lambda: LogisticRegression(max_iter=200),
        lambda: LinearRegression(), rng, folds=2)
    mlv = _dr_did_crossfit(
        dY, treated, X,
        lambda: GradientBoostingClassifier(n_estimators=120, max_depth=3, learning_rate=0.1),
        lambda: GradientBoostingRegressor(n_estimators=120, max_depth=3, learning_rate=0.1),
        rng, folds=2)
    return {
        "key": "dml",
        "title": t(lang, "雙重機器學習 DiD（真的跑 ML）", "Double machine-learning DiD (real ML)"),
        "true_att": true_att, "naive": naive, "linear": lin, "ml": mlv,
        "bars": {"labels": [t(lang, "真值", "Truth"), t(lang, "天真 DiD", "Naive DiD"),
                            t(lang, "線性雙重穩健", "Linear DR"), t(lang, "DML（梯度提升）", "DML (boosting)")],
                 "values": [true_att, naive, lin, mlv]},
        "plain": t(
            lang,
            "這是這個分頁裡<b>唯一真正用到機器學習</b>的地方。情境：是否接種與隨時間的自然變化，都以<b>非線性</b>"
            "的方式取決於好幾個共變項。雙重穩健 DiD 同時配『傾向分數模型』與『結果模型』，只要其一對就不偏；"
            "但如果用<b>線性</b>模型去配這些非線性關係，模型設定錯，估計仍會偏。改用<b>梯度提升（gradient boosting）</b>"
            "這種機器學習去估那兩塊、再用<b>交叉擬合</b>（用別折資料學、套到沒看過的折）去偏，就能把效果拉回真值——"
            "這就是雙重／去偏機器學習（DML）。",
            "This is the <b>only place in this tab that genuinely uses machine learning</b>. Here both who gets "
            "vaccinated and the natural over-time change depend <b>non-linearly</b> on several covariates. Doubly-robust "
            "DiD pairs a propensity model with an outcome model and is unbiased if either is right — but fit those "
            "non-linear relationships with <b>linear</b> models and the misspecification leaves bias. Estimate the two "
            "nuisance pieces with <b>gradient boosting</b> and de-bias with <b>cross-fitting</b> (learn on other folds, "
            "predict on held-out ones) and the estimate returns to the truth — that is double/debiased ML (DML).",
        ),
        "reading": t(
            lang,
            f"天真 DiD ≈ {naive:.2f}；用線性模型的雙重穩健 ≈ {lin:.2f}（非線性設定錯、仍偏）；"
            f"用梯度提升的 DML ≈ {mlv:.2f}，貼回真值 {true_att:.2f}。",
            f"Naive DiD ≈ {naive:.2f}; linear-model DR ≈ {lin:.2f} (still biased — misspecified on non-linearity); "
            f"gradient-boosting DML ≈ {mlv:.2f}, back at the truth {true_att:.2f}.",
        ),
    }


# ===========================================================================
# 2) Staggered adoption — TWFE is biased, cohort-average ATT is clean
# ===========================================================================
def staggered_demo(seed=11, lang="zh"):
    rng = np.random.default_rng(seed)
    T = 6
    cohorts = {2: 12, 4: 12, None: 12}   # adopt at t=2, t=4, never (control)
    # dynamic effect: grows with exposure (so heterogeneous over time)
    def effect(k):  # k = periods since adoption (>=0)
        return 1.5 + 1.0 * k
    rows = []
    uid = 0
    for gstart, m in cohorts.items():
        for _ in range(m):
            fe = rng.normal(0, 3.0)
            for tt in range(T):
                trend = 1.0 * tt
                if gstart is not None and tt >= gstart:
                    eff = effect(tt - gstart)
                else:
                    eff = 0.0
                y = 50 + fe + trend + eff + rng.normal(0, 1.0)
                rows.append((uid, tt, gstart if gstart is not None else -1, y))
            uid += 1
    arr = np.array(rows, dtype=float)
    U, Tt, G, Y = arr[:, 0], arr[:, 1], arr[:, 2], arr[:, 3]

    # --- TWFE: Y ~ unit FE + time FE + treat_now ; coef on treat_now ---
    treat_now = ((G >= 0) & (Tt >= G)).astype(float)
    units = np.unique(U); times = np.unique(Tt)
    cols = [treat_now]
    for u in units[1:]:
        cols.append((U == u).astype(float))
    for tt in times[1:]:
        cols.append((Tt == tt).astype(float))
    cols.append(np.ones_like(Y))
    Xtw = np.column_stack(cols)
    btw = _ols(Xtw, Y)
    twfe = float(btw[0])

    # --- Callaway–Sant'Anna style: average clean ATT(g,t) vs not-yet-treated ---
    att_gt = []
    truth_gt = []
    for gstart in (2, 4):
        for tt in range(int(gstart), T):
            base = gstart - 1
            treated_mask = (G == gstart)
            # controls = not-yet-treated at period tt (never-treated or adopt later)
            ctrl_mask = (G == -1) | (G > tt)
            def cell(mask, period):
                m = mask & (Tt == period)
                return Y[m].mean()
            d_treat = cell(treated_mask, tt) - cell(treated_mask, base)
            d_ctrl = cell(ctrl_mask, tt) - cell(ctrl_mask, base)
            att_gt.append(d_treat - d_ctrl)
            truth_gt.append(effect(tt - gstart))
    cs = float(np.mean(att_gt))
    truth = float(np.mean(truth_gt))

    return {
        "key": "staggered",
        "title": t(lang, "交錯採用（不同時間受處置）", "Staggered adoption (different start times)"),
        "true_att": truth, "twfe": twfe, "cs": cs,
        "bars": {"labels": [t(lang, "真值（平均）", "Truth (avg)"),
                            t(lang, "傳統 TWFE", "Two-way FE"),
                            t(lang, "群組-時間平均", "Cohort-time avg")],
                 "values": [truth, twfe, cs]},
        "scene": {"cohorts": [2, 4, -1]},
        "plain": t(
            lang,
            "情境：不同社區在『不同時間』才陸續上路政策（有的第 2 期、有的第 4 期、有的一直沒有）。"
            "傳統的雙向固定效果（TWFE）迴歸會偷偷拿『已經受處置的單位』當別人的對照，當效果隨時間變化時"
            "會被汙染、甚至估出錯誤方向。改用 Callaway–Sant'Anna 的做法：只用『還沒受處置』的單位當乾淨對照，"
            "分別估每個世代每個時間的效果，再平均，就能還原真值。",
            "Scenario: communities switch the policy on at DIFFERENT times (some at period 2, some at 4, some never). "
            "A conventional two-way fixed-effects (TWFE) regression quietly uses already-treated units as controls for "
            "others; when effects vary over time this contaminates the estimate and can even flip its sign. The "
            "Callaway–Sant'Anna approach uses only NOT-YET-treated units as clean controls, estimates each cohort-by-time "
            "effect, then averages — recovering the truth.",
        ),
        "reading": t(
            lang,
            f"傳統 TWFE ≈ {twfe:.2f}（被交錯時點汙染），群組-時間平均 ≈ {cs:.2f}，貼近真值 {truth:.2f}。",
            f"TWFE ≈ {twfe:.2f} (contaminated by staggered timing); cohort-time average ≈ {cs:.2f}, close to the truth {truth:.2f}.",
        ),
    }


# ===========================================================================
# 3) Universal DiD — binary outcome: additive trends fail, odds-ratio works
# ===========================================================================
def universal_did_demo(seed=5, lang="zh"):
    rng = np.random.default_rng(seed)
    # baseline risks differ; a COMMON multiplicative (odds) time shift hits both;
    # treated also gets a true causal odds ratio. On the risk-difference scale the
    # "parallel" common shift is NOT parallel (bounded by 0/1) -> additive DiD biased.
    true_or = 2.0
    # group baseline log-odds
    lo_treat_pre = -1.6      # ~0.17
    lo_ctrl_pre = 0.2        # ~0.55
    time_shift = 0.8         # common change in log-odds from pre->post
    def p(lo):
        return 1.0 / (1.0 + np.exp(-lo))
    n = 4000
    # simulate four cells
    def risk(lo):
        return p(lo)
    p_tp = risk(lo_treat_pre)
    p_tq = risk(lo_treat_pre + time_shift + np.log(true_or))   # treated post (+ causal OR)
    p_cp = risk(lo_ctrl_pre)
    p_cq = risk(lo_ctrl_pre + time_shift)                       # control post

    # additive (risk-difference) DiD
    add = float((p_tq - p_tp) - (p_cq - p_cp))
    # odds-ratio DiD = ratio of odds-ratios (treated vs control over time)
    def odds(pr):
        return pr / (1 - pr)
    or_treat = odds(p_tq) / odds(p_tp)
    or_ctrl = odds(p_cq) / odds(p_cp)
    or_did = float(or_treat / or_ctrl)

    return {
        "key": "universal",
        "title": t(lang, "Universal DiD（二元／計數結果）", "Universal DiD (binary / count outcomes)"),
        "true_or": true_or, "additive_dd": add, "or_did": or_did,
        "bars": {"labels": [t(lang, "真值 OR", "True OR"), t(lang, "勝算比 DiD", "Odds-ratio DiD")],
                 "values": [true_or, or_did]},
        "scene": {"probs": {"treated": [p_tp, p_tq], "control": [p_cp, p_cq]}},
        "plain": t(
            lang,
            "情境：結果是『是否發生』這種二元事件，而且兩組的基準風險差很多（例如一組 17%、一組 55%）。"
            "就算時間帶來的是『相同的勝算（odds）變化』，換算成『風險差』時，靠近 0 或 1 的那組變動空間被壓縮，"
            "看起來就不平行了——加法版的平行趨勢失效，risk-difference DiD 會偏。Universal DiD 改在『勝算比』尺度上"
            "用 equi-confounding 假設辨識，對二元/計數/順序結果更合適。",
            "Scenario: the outcome is a yes/no event and the two groups have very different baseline risk (say 17% vs 55%). "
            "Even if time brings the SAME change in odds, converting to a risk DIFFERENCE compresses the group near 0 or 1, "
            "so it no longer looks parallel — additive parallel trends fail and a risk-difference DiD is biased. Universal "
            "DiD identifies the effect on the ODDS-RATIO scale (an equi-confounding assumption), which suits binary / count "
            "/ ordinal outcomes.",
        ),
        "reading": t(
            lang,
            f"加法（風險差）DiD 把效果報成 {add:+.3f} 的風險差、看不出真相；勝算比 DiD ≈ {or_did:.2f}，回到真值 OR {true_or:.2f}。",
            f"The additive (risk-difference) DiD reports a {add:+.3f} risk gap and hides the truth; the odds-ratio DiD ≈ {or_did:.2f}, recovering the true OR {true_or:.2f}.",
        ),
    }


# ===========================================================================
# 4) Synthetic control — few treated units, build a weighted counterfactual
# ===========================================================================
def synth_control_demo(seed=3, lang="zh"):
    rng = np.random.default_rng(seed)
    T = 10
    t0 = 6
    n_ctrl = 10
    true_effect = 5.0
    # latent factors drive each unit's path; treated is a blend of some controls
    f1 = np.cumsum(rng.normal(0, 1, T)) + np.linspace(0, 6, T)
    f2 = np.cumsum(rng.normal(0, 1, T))
    controls = []
    loadings = rng.uniform(0, 1, (n_ctrl, 2))
    for i in range(n_ctrl):
        y = 30 + loadings[i, 0] * f1 + loadings[i, 1] * f2 + rng.normal(0, 0.6, T)
        controls.append(y)
    controls = np.array(controls)                       # (n_ctrl, T)
    # treated unit: a convex blend of factors (so a good synthetic exists) + effect post-t0
    w_true = np.array([0.55, 0.45])
    treated = 30 + w_true[0] * f1 + w_true[1] * f2 + rng.normal(0, 0.6, T)
    treated_obs = treated.copy()
    treated_obs[t0:] += true_effect

    # fit non-negative weights summing to 1 on PRE-period to match treated
    Ypre_ctrl = controls[:, :t0].T            # (t0, n_ctrl)
    ypre_treat = treated_obs[:t0]
    def loss(w):
        return float(np.sum((ypre_treat - Ypre_ctrl @ w) ** 2))
    cons = ({"type": "eq", "fun": lambda w: np.sum(w) - 1.0},)
    bnds = [(0, 1)] * n_ctrl
    w0 = np.full(n_ctrl, 1.0 / n_ctrl)
    res = optimize.minimize(loss, w0, method="SLSQP", bounds=bnds, constraints=cons,
                            options={"maxiter": 200, "ftol": 1e-9})
    w = np.clip(res.x, 0, None)
    w = w / w.sum()
    synth = controls.T @ w                     # (T,)
    gap = treated_obs - synth
    est = float(np.mean(gap[t0:]))

    return {
        "key": "synth",
        "title": t(lang, "合成控制／合成 DiD", "Synthetic control / synthetic DiD"),
        "true_effect": true_effect, "estimate": est, "t0": t0,
        "series": {"periods": list(range(T)),
                   "treated": treated_obs.round(3).tolist(),
                   "synth": synth.round(3).tolist()},
        "plain": t(
            lang,
            "情境：受處置的單位只有一個（或很少），找不到單一條件相符的對照。合成控制的做法是："
            "用一堆控制單位的『加權組合』，去擬合受處置單位在政策前的走勢；擬合好之後，把同一組權重套到政策後，"
            "得到的就是『如果沒有政策會怎樣』的反事實。受處置單位與這條合成線在政策後的落差，就是效果。"
            "合成 DiD 再把 DiD 的『差分』與合成控制的『加權』結合，更穩健。",
            "Scenario: there is only one treated unit (or very few), and no single control matches it. Synthetic control "
            "builds a WEIGHTED combination of control units that tracks the treated unit's pre-policy path; applying the "
            "same weights after the policy gives the counterfactual 'what would have happened without the policy'. The gap "
            "between the treated unit and this synthetic line after the policy is the effect. Synthetic DiD further combines "
            "DiD differencing with synthetic-control weighting for extra robustness.",
        ),
        "reading": t(
            lang,
            f"政策後受處置單位高出合成反事實平均約 {est:.2f}，貼近真值 {true_effect:.2f}。",
            f"After the policy the treated unit sits about {est:.2f} above its synthetic counterfactual, close to the truth {true_effect:.2f}.",
        ),
    }


def variant_demos(seed=7, lang="zh"):
    """The advanced DiD VARIANTS (not AI) — shown in tab ③ 資料分析. Light/no sklearn."""
    return {
        "staggered": staggered_demo(seed=seed + 4, lang=lang),
        "universal": universal_did_demo(seed=seed + 1, lang=lang),
        "synth": synth_control_demo(seed=seed + 2, lang=lang),
    }

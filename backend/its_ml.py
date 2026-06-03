"""ITS ⑤『用 AI／進階方法強化』—— 四個輕量教學 demo（小 N、固定種子）。

每個 demo 都鋪一個「樸素 ITS 會在這裡出錯 → 進階方法把它救回來」的故事，回傳比較
數字＋一點圖資料＋雙語白話。全部用 numpy/scipy 從頭實作，可在 Pyodide 跑。

對應四類文獻：
  hac        自相關與 Newey–West/HAC 穩健 SE（Bernal 2017；Schaffer 2021 ARIMA）
  controlled 控制組 ITS／三重差分（Linden 2026 DDD-ITSA）
  flexible   ML 兩階段彈性反事實預測（Dey 2025，Prophet-XGBoost/NNETAR 的精神）
  bsts       貝氏結構時間序列／CausalImpact（Brodersen 等）—— 以概念＋示意呈現
"""
from __future__ import annotations

import numpy as np

import its_core
from i18n import t


def _segmented_level(time, post, t_since, y):
    X = np.column_stack([np.ones_like(y), time, post, t_since])
    beta, resid, XtX_inv = its_core._ols(X, y)
    cov_ols = its_core._ols_se(X, resid, XtX_inv)
    cov_hac, L = its_core.newey_west(X, resid, XtX_inv)
    return float(beta[2]), float(np.sqrt(cov_ols[2, 2])), float(np.sqrt(cov_hac[2, 2])), int(L)


# ===========================================================================
# 1) Autocorrelation & HAC standard errors
# ===========================================================================
def hac_demo(seed=7, lang="zh"):
    rng = np.random.default_rng(seed)
    n, t0 = 48, 24
    time = np.arange(n); post = (time >= t0).astype(int); ts = np.clip(time - t0, 0, None) * post
    true_level = -10.0
    eps = rng.normal(0, 2.5, n)
    for i in range(1, n):
        eps[i] += 0.7 * eps[i - 1]              # strong AR(1)
    y = 100 + 0.4 * time + true_level * post - 0.4 * ts + eps
    lev, se_ols, se_hac, L = _segmented_level(time, post, ts, y)
    return {
        "key": "hac", "title": t(lang, "自相關與 HAC 穩健標準誤", "Autocorrelation & HAC robust SE"),
        "true_level": true_level, "level": lev,
        "se_ols": se_ols, "se_hac": se_hac,
        "ci_ols": [lev - 1.96 * se_ols, lev + 1.96 * se_ols],
        "ci_hac": [lev - 1.96 * se_hac, lev + 1.96 * se_hac],
        "series": {"time": time.tolist(), "y": y.round(2).tolist(), "t0": t0},
        "plain": t(
            lang,
            "情境：時間序列相鄰月份彼此相關（自相關）。點估計沒問題，但<b>天真 OLS 的信賴區間會太窄</b>"
            "——它假設每個月互相獨立，於是低估了不確定性、p 值太漂亮。Newey–West（HAC）穩健標準誤"
            "把這種相關納入，給出<b>較寬、較誠實</b>的區間。",
            "Scenario: adjacent months in a time series are correlated (autocorrelation). The point estimate is fine, "
            "but a <b>naive OLS confidence interval is too narrow</b> — it assumes months are independent, so it "
            "understates uncertainty and the p-values look too good. Newey–West (HAC) robust SEs fold in that "
            "correlation and give a <b>wider, more honest</b> interval.",
        ),
        "reading": t(
            lang,
            f"水準變化點估計 ≈ {lev:.1f}（真值 {true_level:.0f}）。天真 OLS 標準誤 {se_ols:.2f} vs "
            f"HAC 標準誤 {se_hac:.2f}——忽略自相關會讓區間假性變窄。",
            f"Level-change point estimate ≈ {lev:.1f} (truth {true_level:.0f}). Naive OLS SE {se_ols:.2f} vs "
            f"HAC SE {se_hac:.2f} — ignoring autocorrelation makes the interval spuriously narrow.",
        ),
    }


# ===========================================================================
# 2) Controlled ITS / triple-difference — remove a coincident secular event
# ===========================================================================
def controlled_demo(seed=9, lang="zh"):
    rng = np.random.default_rng(seed)
    n, t0 = 48, 24
    time = np.arange(n); post = (time >= t0).astype(int); ts = np.clip(time - t0, 0, None) * post
    true_level = -10.0
    coincident = 7.0       # a secular event ALSO drops/raises both series at t0
    treated = 100 + 0.4 * time + true_level * post + coincident * post + rng.normal(0, 2.0, n)
    control = 90 + 0.4 * time + coincident * post + rng.normal(0, 2.0, n)  # no intervention effect
    unc, _, _, _ = _segmented_level(time, post, ts, treated)               # biased by coincident
    con, _, _, _ = _segmented_level(time, post, ts, treated - control)     # difference removes it
    return {
        "key": "controlled", "title": t(lang, "控制組 ITS／三重差分", "Controlled ITS / triple difference"),
        "true_level": true_level, "uncontrolled": unc, "controlled": con,
        "series": {"time": time.tolist(), "treated": treated.round(2).tolist(),
                   "control": control.round(2).tolist(), "t0": t0},
        "plain": t(
            lang,
            "情境：就在介入的同一個月，另一件時代大事也讓指標跳了一下（季節、通報改變、疫情……）。"
            "<b>沒有控制組</b>的 ITS 會把這個共時跳變全算到介入頭上而高估／低估。加入一條<b>不受介入影響、"
            "但同樣被那件大事影響</b>的控制序列，做『介入序列減控制序列』的差分，就把共時變化消掉，"
            "剩下介入真正的效果（這就是控制組 ITS／三重差分的精神）。",
            "Scenario: in the very month of the intervention, another big contemporaneous event also shifts the metric "
            "(season, reporting change, epidemic…). An <b>uncontrolled</b> ITS blames that shared jump entirely on the "
            "intervention and is biased. Add a control series that is <b>unaffected by the intervention but hit by the "
            "same event</b>, and take 'treated minus control' — the shared shift cancels, leaving the intervention's true "
            "effect (the idea behind controlled ITS / triple difference).",
        ),
        "reading": t(
            lang,
            f"未控制的 ITS 水準變化 ≈ {unc:.1f}（被共時事件汙染），控制組差分後 ≈ {con:.1f}，貼近真值 {true_level:.0f}。",
            f"Uncontrolled ITS level change ≈ {unc:.1f} (contaminated by the coincident event); after the controlled "
            f"difference ≈ {con:.1f}, close to the truth {true_level:.0f}.",
        ),
    }


# ===========================================================================
# 3) Flexible (ML two-stage) counterfactual vs straight-line extrapolation
# ===========================================================================
def mlcf_demo(seed=5, lang="zh"):
    """⑤ ITS — a GENUINE machine-learning counterfactual (Dey 2025 two-stage): train
    a model on the PRE period to predict the outcome from observed covariates, then
    forecast the POST counterfactual. The counterfactual depends NON-LINEARLY (with an
    interaction) on two covariates whose mix shifts after the intervention, so a linear
    model is biased while gradient boosting recovers the true effect."""
    from sklearn.ensemble import GradientBoostingRegressor
    from sklearn.linear_model import LinearRegression
    rng = np.random.default_rng(seed)
    n, t0 = 96, 60
    time = np.arange(n)
    post = (time >= t0).astype(int)
    true_level = -10.0
    # several observed covariates (e.g. background-illness markers) whose mix drifts
    # modestly after the intervention; the no-intervention outcome depends on them
    # NON-LINEARLY with interactions, so a linear adjustment is biased while gradient
    # boosting recovers the truth. Modest in-range shift -> the ML model interpolates.
    shift = np.where(post == 1, 0.8, 0.0)
    X = rng.normal(0, 1, (n, 3)) + shift[:, None]
    seas = 0.6 * np.sin(2 * np.pi * time / 12.0)
    cf_true = (60 + seas + 2.6 * np.sin(1.6 * X[:, 0]) + 1.3 * X[:, 1] ** 2
               + 0.9 * X[:, 0] * X[:, 1] - 1.1 * X[:, 2] + rng.normal(0, 0.8, n))
    y = cf_true + true_level * post

    ts = np.clip(time - t0, 0, None) * post
    naive_level, _, _, _ = _segmented_level(time, post, ts, y)   # time-only -> ignores covariate drift

    Z = np.column_stack([X, seas])
    pre = post == 0
    lin = LinearRegression().fit(Z[pre], y[pre])
    gb = GradientBoostingRegressor(n_estimators=250, max_depth=3, learning_rate=0.07).fit(Z[pre], y[pre])
    cf_lin = lin.predict(Z)
    cf_ml = gb.predict(Z)
    lin_level = float(np.mean(y[post == 1] - cf_lin[post == 1]))
    ml_level = float(np.mean(y[post == 1] - cf_ml[post == 1]))
    return {
        "key": "mlcf", "title": t(lang, "ML 兩階段反事實預測（真的跑 ML）", "ML two-stage counterfactual (real ML)"),
        "true_level": true_level, "naive": float(naive_level), "linear": lin_level, "ml": ml_level,
        "bars": {"labels": [t(lang, "真值", "Truth"), t(lang, "天真 ITS", "Naive ITS"),
                            t(lang, "線性反事實", "Linear CF"), t(lang, "ML 反事實", "ML CF")],
                 "values": [true_level, float(naive_level), lin_level, ml_level]},
        "series": {"time": time.tolist(), "y": y.round(2).tolist(),
                   "cf": cf_ml.round(2).tolist(), "t0": t0},
        "plain": t(
            lang,
            "這是這個分頁裡<b>唯一真正用到機器學習</b>的地方。情境：沒有介入時，每月的健康指標其實由幾個"
            "<b>可觀測的共變項</b>非線性地決定（例如季節性的背景呼吸道疾病指數、以及『是否有共同流行的病毒』，"
            "兩者還會交互作用）；而『有共同流行病毒』在介入後的那段時間剛好變多。樸素 ITS 只看時間、不看共變項，"
            "會把這個共變項造成的變化誤當成介入效果。兩階段做法（Dey 2025）：只用<b>介入前</b>資料訓練一個模型"
            "去學『共變項→結果』，再用介入後觀測到的共變項預測『沒介入會怎樣』的反事實。<b>線性</b>模型抓不到"
            "交互作用、仍偏；改用<b>梯度提升</b>這種機器學習就抓得到，把效果拉回真值。模型只准看介入前、不准碰介入後。",
            "This is the <b>only place in this tab that genuinely uses machine learning</b>. Absent the intervention, the "
            "monthly health index is actually driven <b>non-linearly</b> by a few observed covariates (a seasonal "
            "background-illness index and whether a co-circulating virus is present, which also interact); and the "
            "co-circulating virus happens to be more common during the post period. A naive ITS that looks only at time "
            "mistakes that covariate-driven change for an intervention effect. The two-stage fix (Dey 2025): train a model "
            "on the <b>pre</b> period to learn covariates→outcome, then use the post-period covariates to predict the "
            "no-intervention counterfactual. A <b>linear</b> model misses the interaction and stays biased; <b>gradient "
            "boosting</b> captures it and recovers the truth. The model may see only the pre period, never the post.",
        ),
        "reading": t(
            lang,
            f"天真 ITS 水準變化 ≈ {naive_level:.1f}（被共變項變化汙染）；線性反事實 ≈ {lin_level:.1f}（漏掉交互作用、仍偏）；"
            f"ML 反事實 ≈ {ml_level:.1f}，貼回真值 {true_level:.0f}。",
            f"Naive ITS level change ≈ {naive_level:.1f} (contaminated by the covariate shift); linear counterfactual "
            f"≈ {lin_level:.1f} (misses the interaction, still biased); ML counterfactual ≈ {ml_level:.1f}, back at the "
            f"truth {true_level:.0f}.",
        ),
    }


# ===========================================================================
# 4) Bayesian structural time series (CausalImpact) — concept + illustration
# ===========================================================================
def bsts_demo(seed=3, lang="zh"):
    rng = np.random.default_rng(seed)
    n, t0 = 48, 24
    time = np.arange(n); post = time >= t0
    true_level = -9.0
    y = 100 + 0.4 * time + true_level * post + rng.normal(0, 2.0, n)
    # illustrative counterfactual with an uncertainty band (pre-trend ± widening band)
    b = np.polyfit(time[~post], y[~post], 1)
    cf = np.polyval(b, time)
    sd = y[~post].std()
    band = sd * (1 + 0.06 * np.clip(time - t0, 0, None))      # band widens after t0
    return {
        "key": "bsts", "title": t(lang, "貝氏結構時間序列（CausalImpact）", "Bayesian structural time series (CausalImpact)"),
        "concept": True, "true_level": true_level,
        "series": {"time": time.tolist(), "y": y.round(2).tolist(),
                   "cf": cf.round(2).tolist(),
                   "lo": (cf - 1.96 * band).round(2).tolist(),
                   "hi": (cf + 1.96 * band).round(2).tolist(), "t0": t0},
        "plain": t(
            lang,
            "概念（文獻有提到、但這些論文未細述，故以示意呈現）：貝氏結構時間序列（如 Brodersen 等人的"
            "<b>CausalImpact</b>）把『趨勢＋季節＋可用的對照預測變數』寫成一個狀態空間模型，自動學出"
            "<b>反事實的整條後驗分布</b>，而不只是一個點。好處是：反事實帶有<b>會隨時間變寬的不確定帶</b>"
            "（離介入越遠越不確定，如圖中陰影），效果與其可信區間都更誠實；也能自然納入多條對照序列。",
            "Concept (mentioned in the literature but not detailed in these papers, so shown illustratively): a Bayesian "
            "structural time series — e.g. Brodersen et al.'s <b>CausalImpact</b> — writes 'trend + seasonality + useful "
            "control predictors' as a state-space model and learns the <b>entire posterior distribution of the "
            "counterfactual</b>, not just a point. The payoff: the counterfactual carries an <b>uncertainty band that "
            "widens over time</b> (further from the intervention is less certain, as shaded), so the effect and its "
            "credible interval are more honest; multiple control series fold in naturally.",
        ),
        "reading": t(
            lang,
            "圖中陰影是『沒介入會怎樣』的後驗不確定帶，離介入越遠越寬——這正是 CausalImpact 比單一直線反事實"
            "更誠實的地方。（此處為示意，非完整貝氏推論。）",
            "The shaded band is the posterior uncertainty of 'what would have happened without the intervention', "
            "widening with distance from the intervention — exactly where CausalImpact is more honest than a single "
            "straight-line counterfactual. (Illustrative here, not a full Bayesian fit.)",
        ),
    }


def variant_demos(seed=7, lang="zh"):
    """The advanced ITS VARIANTS (not AI) — shown in tab ③ 資料分析. Light/no sklearn."""
    return {
        "hac": hac_demo(seed=seed, lang=lang),
        "controlled": controlled_demo(seed=seed + 2, lang=lang),
        "bsts": bsts_demo(seed=seed + 3, lang=lang),
    }

"""ACNU ⑤『用 AI 強化』—— a GENUINE machine-learning demo (real scikit-learn).

對應文獻：Schneeweiss et al. (2009, Epidemiology 20:512) 的高維傾向分數（hdPS）與後續用
<b>機器學習估計傾向分數</b>的工作（如 gradient boosting / Lee, Lessler & Stuart 2010）。
教學重點：主動對照新使用者設計把大半混淆削掉後，<b>殘留混淆</b>要用傾向分數（PS）校正。當『拿 A 還是
拿對照藥 B』的決定和共變項是<b>非線性</b>關係（交互作用／閾值）時，只放主效應的<b>邏輯斯 PS</b> 會
<b>設定錯誤、校正不乾淨、留下殘餘偏誤</b>；改用<b>梯度提升</b>估 PS 能抓到非線性、把速率比拉回真值。
"""
from __future__ import annotations

import numpy as np

from i18n import t


def _wirr(event, fut, isA, w):
    """Weighted incidence-rate ratio A vs B using IPTW weights w."""
    eA = float(np.sum(w[isA] * event[isA])); tA = float(np.sum(w[isA] * fut[isA]))
    eB = float(np.sum(w[~isA] * event[~isA])); tB = float(np.sum(w[~isA] * fut[~isA]))
    if tA <= 0 or tB <= 0 or eB <= 0:
        return float("nan")
    return (eA / tA) / (eB / tB)


def ps_ml_demo(seed=41, lang="zh"):
    """Real sklearn. New users of A vs active-comparator B, where the A-vs-B CHOICE depends
    NON-LINEARLY on covariates (a severity×age interaction with a threshold) and severity also
    drives the outcome. A main-effects LOGISTIC propensity score is mis-specified → IPTW leaves
    residual confounding; a GRADIENT-BOOSTING propensity score captures the non-linearity →
    IPTW recovers the truth. Compared on the same data."""
    from sklearn.linear_model import LogisticRegression
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.metrics import roc_auc_score

    rng = np.random.default_rng(seed)
    n = 24000
    true_hr = 1.6
    age = rng.integers(45, 85, n).astype(float)
    sev = rng.normal(0, 1, n)
    az = (age - 65) / 10.0
    # A-vs-B choice is strongly NON-LINEAR: severity×age interaction + severity thresholds
    logit_A = (-0.1 + 2.0 * sev * (az > 0).astype(float) + 1.6 * (sev > 0.6).astype(float)
               - 0.5 * az - 1.4 * (sev < -0.6).astype(float))
    isA = rng.random(n) < (1.0 / (1.0 + np.exp(-logit_A)))
    # outcome hazard: severity (confounder, non-linear) + drug A multiplies by true_hr
    lam = 0.10 * np.exp(0.95 * sev + 0.35 * (sev ** 2 - 1.0)) * np.where(isA, true_hr, 1.0)
    lam = np.clip(lam, 1e-4, None)
    evt_time = rng.exponential(1.0 / lam)
    fut = np.minimum(evt_time, 2.0)
    event = (evt_time <= 2.0).astype(float)

    # main effects only → a linear PS cannot represent the thresholds/interaction; the
    # boosting PS can split on them.
    X = np.column_stack([sev, az])
    y = isA.astype(int)
    ntr = int(0.6 * n); idx = rng.permutation(n); tr = idx[:ntr]

    lin = LogisticRegression(max_iter=300).fit(X[tr], y[tr])
    gb = GradientBoostingClassifier(n_estimators=300, max_depth=3, learning_rate=0.05,
                                    subsample=0.8, random_state=seed).fit(X[tr], y[tr])
    ps_lin = np.clip(lin.predict_proba(X)[:, 1], 0.02, 0.98)
    ps_gb = np.clip(gb.predict_proba(X)[:, 1], 0.02, 0.98)
    auc_lin = float(roc_auc_score(y, ps_lin)); auc_gb = float(roc_auc_score(y, ps_gb))

    pA = float(y.mean())
    def stab_w(ps):
        return np.where(isA, pA / ps, (1 - pA) / (1 - ps))
    irr_unadj = _wirr(event, fut, isA, np.ones(n))
    irr_lin = _wirr(event, fut, isA, stab_w(ps_lin))
    irr_gb = _wirr(event, fut, isA, stab_w(ps_gb))

    return {
        "key": "acnu_ps_ml",
        "title": t(lang, "機器學習傾向分數：把殘留混淆校乾淨（真的跑 ML）",
                   "ML propensity score: clean up residual confounding (real ML)"),
        "auc_logistic": round(auc_lin, 3), "auc_gb": round(auc_gb, 3),
        "true_hr": true_hr,
        "irr_unadj": round(irr_unadj, 2), "irr_logistic": round(irr_lin, 2), "irr_gb": round(irr_gb, 2),
        "bars": {"labels": [t(lang, "未校正（粗 ACNU）", "unadjusted (crude ACNU)"),
                            t(lang, "邏輯斯 PS（主效應）", "logistic PS (main effects)"),
                            t(lang, "梯度提升 PS", "gradient-boosting PS"),
                            t(lang, "真值", "truth")],
                 "values": [round(irr_unadj, 2), round(irr_lin, 2), round(irr_gb, 2), true_hr]},
        "plain": t(
            lang,
            "主動對照削掉大半混淆後，A 與 B 之間還有<b>殘留混淆</b>要用<b>傾向分數（PS）</b>校正。"
            "這裡『拿 A 還是 B』的決定和共變項是<b>非線性</b>關係（嚴重度 × 年齡的閾值交互作用）。只放主效應的"
            "<b>邏輯斯 PS</b> 設定錯誤、校正不乾淨，速率比仍偏；改用<b>梯度提升</b>估 PS（hdPS／ML-PS 的精神）"
            "抓到非線性，IPTW 加權後把速率比拉回<b>真值</b>。這是本頁真的呼叫 scikit-learn 的地方。",
            "After the active comparator removes most confounding, A and B still carry <b>residual confounding</b> to be "
            "adjusted with a <b>propensity score (PS)</b>. Here the A-vs-B choice depends <b>non-linearly</b> on covariates "
            "(a severity × age threshold interaction). A main-effects <b>logistic PS</b> is mis-specified and adjusts "
            "imperfectly, so the rate ratio stays biased; a <b>gradient-boosting PS</b> (the spirit of hdPS / ML-PS) captures "
            "the non-linearity, and IPTW weighting pulls the rate ratio back to the <b>truth</b>. This is where the page really "
            "calls scikit-learn.",
        ),
        "reading": t(
            lang,
            f"未校正的粗 ACNU ≈ {irr_unadj:.2f}；主效應<b>邏輯斯 PS</b> 校正後 ≈ {irr_lin:.2f}（仍偏，PS 設定錯誤，"
            f"判別 AUC ≈ {auc_lin:.3f}）；<b>梯度提升 PS</b> ≈ {irr_gb:.2f}（AUC ≈ {auc_gb:.3f}）——貼回真值 {true_hr:.2f}。",
            f"Crude ACNU ≈ {irr_unadj:.2f}; main-effects <b>logistic PS</b> ≈ {irr_lin:.2f} (still biased — mis-specified PS, "
            f"AUC ≈ {auc_lin:.3f}); <b>gradient-boosting PS</b> ≈ {irr_gb:.2f} (AUC ≈ {auc_gb:.3f}) — back on the truth {true_hr:.2f}.",
        ),
    }

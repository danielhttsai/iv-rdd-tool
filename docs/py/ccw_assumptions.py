"""Clone-Censor-Weight (CCW) assumption checks C1–C5 — following Hernán (2018),
Maringe et al. (2020), Gaber et al. (2024). Like other target-trial methods, the
core identifying assumptions are untestable from data alone, so we are honest
(blue 'info' cards) and surface the diagnostics that ARE checkable: positivity
(overlap), the weight distribution, and enough events.

Each check returns {id, title, status, headline, plain, term, metrics:[...]};
run_dashboard returns {"checks": [...]}.
"""
from __future__ import annotations

import numpy as np

import ccw_core
from i18n import t


def run_dashboard(df, vacc_time="vacc_month", event="event", futime="futime",
                  covariates=("age", "frailty"), grace=3, horizon=12, lang="zh"):
    res = ccw_core.full_ccw(df, vacc_time, event, futime, covariates, grace, horizon, lang=lang)
    vacc = np.asarray(df[vacc_time], dtype=float)
    early = (~np.isnan(vacc)) & (vacc <= grace)
    checks = [
        _c1_exchangeability(res, lang),
        _c2_positivity(df, early, covariates, lang),
        _c3_consistency(grace, lang),
        _c4_weight_model(res, lang),
        _c5_alignment(res, lang),
    ]
    return {"checks": checks}


def _c1_exchangeability(res, lang="zh"):
    naive, ccw = res["naive"], res["ccw"]
    metrics = [
        {"name": t(lang, "天真 vs CCW 的差距", "Gap between naive and CCW"),
         "value": f"{naive:+.2f} vs {ccw:+.2f}",
         "note": t(lang, "差距大代表混淆／immortal-time 的校正幅度大",
                   "a large gap means a large correction for confounding / immortal time")},
    ]
    return {
        "id": "C1",
        "title": t(lang, "策略內可交換嗎？（無未測混淆，關鍵、不可檢驗）",
                   "Exchangeability within strategy? (no unmeasured confounding — key, untestable)"),
        "status": "info",
        "headline": t(lang, "CCW 假設『誰遵循哪個策略』只由可測共變項決定；這無法用資料證明，要靠領域知識與設計。",
                      "CCW assumes who follows which strategy is governed only by measured covariates; this cannot be proven from data — rely on domain knowledge and design."),
        "plain": t(
            lang,
            "複製-設限-加權能還原因果效應，靠的是『在加權之後，早策略與晚策略的人在所有會影響結果的因素上"
            "可比』（可交換性／無未測混淆）。我們已用可測共變項（年齡、體弱程度）建立反設限權重；但如果還有"
            "<b>沒測到</b>的因素（例如疾病嚴重度的細節）同時影響『何時接種』與『結果』，CCW 仍會有偏。做法："
            "①盡量蒐集並納入重要共變項；②做未測混淆的敏感度分析（如 E-value）；③與隨機試驗對照。",
            "Clone-censor-weight recovers the causal effect by assuming that, after weighting, people following the "
            "early vs late strategy are comparable on everything that affects the outcome (exchangeability / no "
            "unmeasured confounding). We built the censoring weights from measured covariates (age, frailty); but if "
            "an <b>unmeasured</b> factor (e.g. fine-grained disease severity) drives both the timing of vaccination and "
            "the outcome, CCW is still biased. Remedy: ① measure and include the important confounders; ② run an "
            "unmeasured-confounding sensitivity analysis (e.g. E-value); ③ benchmark against a randomized trial.",
        ),
        "term": t(lang, "專有名詞：可交換性（exchangeability）／無未測混淆（no unmeasured confounding）；目標試驗模擬（target trial emulation）。",
                  "Term: exchangeability / no unmeasured confounding; target trial emulation."),
        "metrics": metrics,
    }


def _c2_positivity(df, early, covariates, lang="zh"):
    # positivity = within covariate strata, BOTH strategies are followed (nonzero prob)
    worst = 1.0
    rows = []
    for c in covariates:
        v = np.asarray(df[c], dtype=float)
        # stratify into low/high (median split for continuous; values for binary)
        uniq = np.unique(v)
        if uniq.size <= 2:
            groups = [(f"{c}={int(u)}", v == u) for u in uniq]
        else:
            med = np.median(v)
            groups = [(f"{c}≤median", v <= med), (f"{c}>median", v > med)]
        for name, mask in groups:
            if mask.sum() == 0:
                continue
            share_early = float(early[mask].mean())
            worst = min(worst, share_early, 1.0 - share_early)
            rows.append((name, share_early))
    metrics = [{"name": t(lang, f"早策略比例（{nm}）", f"Early-strategy share ({nm})"),
                "value": f"{sh*100:.0f}%",
                "note": t(lang, "太接近 0% 或 100% → 該層幾乎只走一種策略（違反正性）",
                          "near 0% or 100% means that stratum almost only follows one strategy (positivity violation)")}
               for nm, sh in rows]
    if worst >= 0.10:
        status = "green"
        head = t(lang, "每個共變項層裡，早策略與晚策略都有足夠的人 —— 正性大致成立、權重穩定。",
                 "Every covariate stratum has enough people on both strategies — positivity holds and weights are stable.")
    elif worst >= 0.03:
        status = "amber"
        head = t(lang, "某些層裡，一種策略的人偏少 —— 權重會偏大、估計較不穩。",
                 "In some strata one strategy is sparse — weights get large and the estimate is less stable.")
    else:
        status = "red"
        head = t(lang, "某些層幾乎只走一種策略（近乎違反正性）—— CCW 在那些人身上幾乎無法外推。",
                 "Some strata almost only follow one strategy (near positivity violation) — CCW can barely extrapolate there.")
    return {
        "id": "C2",
        "title": t(lang, "正性（positivity）：每種人都可能走每種策略嗎？（可檢驗）",
                   "Positivity: could every kind of person follow every strategy? (testable)"),
        "status": status, "headline": head,
        "plain": t(
            lang,
            "反設限加權要成立，必須『不論共變項長相，跟隨早策略與晚策略的機率都大於 0』（正性）。如果某種人"
            "（例如最體弱者）幾乎一定早接種、幾乎沒有人晚接種，那一層就沒有可比的對照，權重會爆大、估計不穩。"
            "上面列出各共變項層的『早策略比例』；越接近 0% 或 100% 越危險。",
            "For the censoring weights to work, every kind of person must have a probability above 0 of following both "
            "the early AND the late strategy (positivity). If some people (say the frailest) almost always vaccinate "
            "early and almost none defer, that stratum has no comparable controls, the weights blow up, and the estimate "
            "is unstable. Above are the early-strategy shares per covariate stratum; the closer to 0% or 100%, the more "
            "dangerous.",
        ),
        "term": t(lang, "專有名詞：正性／實證等値（positivity）；共變項重疊（covariate overlap）。",
                  "Term: positivity; covariate overlap."),
        "metrics": metrics,
    }


def _c3_consistency(grace, lang="zh"):
    return {
        "id": "C3",
        "title": t(lang, "策略定義清楚、寬限期合理嗎？（一致性，靠設計）",
                   "Are the strategies well-defined and the grace period sensible? (consistency — by design)"),
        "status": "info",
        "headline": t(lang, f"早／晚策略與寬限期（這裡 g={grace} 個月）必須事先、明確地定義；一致性靠研究設計保證。",
                      f"The early/late strategies and the grace period (here g={grace} months) must be defined in advance and unambiguously; consistency is ensured by design."),
        "plain": t(
            lang,
            "CCW 的『複製』要成立，前提是兩個策略寫得夠清楚，讓每個人在每個時點都能判斷『有沒有偏離』。"
            "<b>寬限期 g</b> 是關鍵設計選擇：在 g 之內還沒接種、也還沒發生事件的人，同時相容於早與晚兩個策略"
            "（所以被複製到兩臂）；到了 g 才依實際行為決定歸屬。g 太短會排除很多人、g 太長會讓『早』與『晚』"
            "變得太像。應做不同 g 的敏感度分析。",
            "For the 'clone' step to be valid, both strategies must be written clearly enough that, at every time, you "
            "can tell whether a person has deviated. The <b>grace period g</b> is a key design choice: someone still "
            "event-free and untreated within g is compatible with BOTH the early and late strategy (so they are cloned "
            "into both arms); only at g is their arm resolved by what they actually did. Too short a g excludes many "
            "people; too long makes 'early' and 'late' too similar. Report a sensitivity analysis over g.",
        ),
        "term": t(lang, "專有名詞：一致性（consistency）；寬限期（grace period）；明確定義的策略（well-defined strategies）。",
                  "Term: consistency; grace period; well-defined strategies."),
        "metrics": [],
    }


def _c4_weight_model(res, lang="zh"):
    we = res["weights"]["early"]; wl = res["weights"]["late"]
    mx = max(we["max"], wl["max"]); fx = max(we["frac_extreme"], wl["frac_extreme"])
    metrics = [
        {"name": t(lang, "穩定化權重平均（早／晚）", "Mean stabilized weight (early/late)"),
         "value": f"{we['mean']:.2f} / {wl['mean']:.2f}",
         "note": t(lang, "應接近 1；明顯偏離代表模型設定可疑", "should be ≈ 1; far from 1 means a suspect model")},
        {"name": t(lang, "最大權重", "Largest weight"), "value": round(mx, 1),
         "note": t(lang, "過大（如 >20）代表少數人主導估計", "very large (e.g. >20) means a few people dominate")},
        {"name": t(lang, "極端權重比例（>10）", "Share of extreme weights (>10)"), "value": f"{fx*100:.1f}%",
         "note": t(lang, "越高越不穩；可截斷或改善模型", "the higher the less stable; trim or improve the model")},
    ]
    if mx <= 12 and fx <= 0.01:
        status = "green"
        head = t(lang, "穩定化權重平均接近 1、沒有極端值 —— 反設限模型行為健康。",
                 "Stabilized weights average ≈ 1 with no extremes — the censoring model behaves well.")
    elif mx <= 30 and fx <= 0.05:
        status = "amber"
        head = t(lang, "權重有些偏大 —— 估計受少數人影響，建議截斷或加強模型。",
                 "Some large weights — a few people sway the estimate; consider trimming or a better model.")
    else:
        status = "red"
        head = t(lang, "權重極端 —— 反設限模型可能設定錯誤或正性不足，CCW 不穩。",
                 "Extreme weights — the censoring model may be mis-specified or positivity is poor; CCW is unstable.")
    return {
        "id": "C4",
        "title": t(lang, "反設限權重模型合理嗎？（可檢驗）",
                   "Is the censoring-weight model reasonable? (testable)"),
        "status": status, "headline": head,
        "plain": t(
            lang,
            "人為設限（偏離策略）不是隨機的，所以我們用<b>反設限機率加權（IPCW）</b>把它補回來。如果這個權重"
            "模型設定正確，<b>穩定化權重的平均應該接近 1</b>，而且不該有少數人帶著超大的權重主宰整個估計。"
            "上面的診斷就是在看這件事；若權重很極端，通常代表模型設定錯誤或正性不足。",
            "Artificial censoring (deviating from a strategy) is not random, so we correct for it with "
            "<b>inverse-probability-of-censoring weighting (IPCW)</b>. If that weight model is correctly specified, the "
            "<b>stabilized weights should average ≈ 1</b>, and no handful of people should carry huge weights that "
            "dominate the estimate. The diagnostics above check exactly this; very extreme weights usually signal "
            "mis-specification or poor positivity.",
        ),
        "term": t(lang, "專有名詞：反設限機率加權（IPCW）；穩定化權重（stabilized weights）；權重截斷（truncation）。",
                  "Term: inverse-probability-of-censoring weighting (IPCW); stabilized weights; truncation."),
        "metrics": metrics,
    }


def _c5_alignment(res, lang="zh"):
    naive, ccw = res["naive"], res["ccw"]
    gap = naive - ccw
    metrics = [
        {"name": t(lang, "天真 − CCW（immortal-time 的指紋）", "Naive − CCW (the immortal-time fingerprint)"),
         "value": f"{gap:+.2f}",
         "note": t(lang, "不為 0 代表天真分組確實受 immortal-time／混淆汙染",
                   "non-zero means the naive grouping really was contaminated by immortal time / confounding")},
    ]
    return {
        "id": "C5",
        "title": t(lang, "時間零點、資格、指派有對齊嗎？（immortal-time，靠設計）",
                   "Are time-zero, eligibility and assignment aligned? (immortal time — by design)"),
        "status": "info",
        "headline": t(lang, "CCW 在『時間零點』就把每個人複製並指派，從源頭消除 immortal-time bias —— 靠正確對齊設計保證。",
                      "CCW clones and assigns everyone at time zero, removing immortal-time bias at the source — ensured by correct alignment in the design."),
        "plain": t(
            lang,
            "immortal-time bias 來自『用未來資訊（最後是早接種還是晚接種）回頭分組』，被歸到早接種的人必須先活著"
            "沒事件，看起來假性更健康。CCW 的解法是：在<b>時間零點（診斷當下）</b>就把每個人複製到兩個策略、"
            "並在偏離時才設限——『死掉或先發生事件的人不會偏離被指派的策略』（Hernán 2018）。上面的"
            "『天真 − CCW』差距，正是這份 immortal-time／混淆被校正掉的證據。前提是設計上正確對齊"
            "<b>時間零點、資格條件、策略指派</b>三者。",
            "Immortal-time bias comes from grouping people using future information (whether they ended up early or "
            "late); those labelled 'early' had to survive event-free first, so they look spuriously healthier. CCW's fix "
            "is to clone every person into both strategies at <b>time zero (the moment of diagnosis)</b> and only censor "
            "on deviation — 'people who die or have the event first do not deviate from their assigned strategy' "
            "(Hernán 2018). The 'naive − CCW' gap above is the evidence of that immortal-time/confounding being "
            "corrected. It requires aligning <b>time zero, eligibility, and treatment assignment</b> correctly in the "
            "design.",
        ),
        "term": t(lang, "專有名詞：immortal-time bias；時間零點對齊（time-zero alignment）；目標試驗模擬（target trial emulation）。",
                  "Term: immortal-time bias; time-zero alignment; target trial emulation."),
        "metrics": metrics,
    }

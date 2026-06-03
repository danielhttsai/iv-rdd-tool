"""Trend-in-trend assumption checks A1-A5 — the analogue of the IV / RDD / DiD
dashboards, following Ji, Small, Leonard & Hennessy (2017).

白話文優先：每一項先用日常語言說明在檢查什麼、結果代表什麼，專有名詞放到 `term`。
TiT 最關鍵的假設（A4：沒有與暴露趨勢跨層相關的未測混淆趨勢）無法用資料證明，我們誠實
標示；其餘可測（暴露趨勢夠強、結果夠罕見、共變項不隨時間漂、模型可乘分離）一併提供。

Each check returns {id, title, status, headline, plain, term, metrics:[...]};
run_dashboard returns {"checks": [...]}; the front-end computes the worst status.
"""
from __future__ import annotations

import numpy as np

import tit_core
from i18n import t


def run_dashboard(df, covariates=("x1", "x2"), K=5, lang="zh"):
    strat_map, auc = tit_core.cpe_strata(df, list(covariates), K=K)
    cells = tit_core.build_cells(df, strat_map, K=K)
    periods = cells["periods"]
    expo_overall = np.array([float(cells["p"][cells["t"] == tp].mean()) for tp in periods])
    out_rate = float(df["outcome"].mean())

    checks = [
        _a1_trend(expo_overall, lang),
        _a2_rare(out_rate, lang),
        _a3_covariate_trend(df, list(covariates), periods, lang),
        _a4_confounder_trend(lang),
        _a5_multiplicative(auc, lang),
    ]
    return {"checks": checks, "K": K}


def _a1_trend(expo_overall, lang="zh"):
    change = float(expo_overall[-1] - expo_overall[0])
    metrics = [
        {"name": t(lang, "暴露盛行率：期初 → 期末", "Exposure prevalence: first → last period"),
         "value": f"{expo_overall[0]*100:.0f}% → {expo_overall[-1]*100:.0f}%",
         "note": t(lang, "差距越大，工具越有力", "the bigger the change, the more powerful the design")},
        {"name": t(lang, "整段變化幅度", "Total change"),
         "value": f"{change*100:.0f} %pt",
         "note": t(lang, "建議 ≥ 10 個百分點", "ideally ≥ 10 percentage points")},
    ]
    if change >= 0.10:
        status = "green"
        head = t(lang, "暴露盛行率隨時間有明顯趨勢，trend-in-trend 有足夠的訊號可用。",
                 "Exposure prevalence trends clearly over time — the design has enough signal.")
    elif change >= 0.05:
        status = "amber"
        head = t(lang, "暴露趨勢偏弱，估計會比較不穩、檢定力低。",
                 "The exposure trend is weak — the estimate will be unstable with low power.")
    else:
        status = "red"
        head = t(lang, "幾乎沒有暴露趨勢，trend-in-trend 失去識別基礎，不建議使用。",
                 "Almost no exposure trend — trend-in-trend loses its identifying basis; not advisable.")
    return {
        "id": "A1",
        "title": t(lang, "暴露隨時間有夠強的趨勢嗎？", "Does exposure trend strongly enough over time?"),
        "status": status, "headline": head,
        "plain": t(
            lang,
            "trend-in-trend 的整個識別力都來自『暴露盛行率隨日曆時間上升』這個趨勢——而且不同 CPE 層"
            "上升的速度不同。趨勢越強，能用來識別因果的訊號越多；如果暴露率幾乎不動（例如老藥、"
            "普及率早就穩定），這個方法就沒東西可用。這是它最大的前提，也是它檢定力的主要來源。",
            "Trend-in-trend draws ALL of its identifying power from the rise in exposure prevalence over "
            "calendar time — rising at different rates across CPE strata. The stronger the trend, the more signal "
            "there is to identify the effect; if exposure barely moves (an old drug at stable uptake) the method has "
            "nothing to work with. This is its biggest premise and the main driver of its power.",
        ),
        "term": t(lang, "專有名詞：暴露盛行率的時間趨勢（temporal trend in exposure prevalence）。",
                  "Term: temporal trend in exposure prevalence."),
        "metrics": metrics,
    }


def _a2_rare(out_rate, lang="zh"):
    metrics = [
        {"name": t(lang, "整體結果發生率", "Overall outcome rate"),
         "value": f"{out_rate*100:.1f}%",
         "note": t(lang, "建議 < 5%（罕見結果近似才成立）",
                   "ideally < 5% (the rare-outcome approximation)")},
    ]
    if out_rate < 0.05:
        status = "green"
        head = t(lang, "結果夠罕見，勝算比≈相對風險的近似成立。",
                 "The outcome is rare enough — the odds-ratio ≈ risk-ratio approximation holds.")
    elif out_rate < 0.10:
        status = "amber"
        head = t(lang, "結果不算很罕見，估計的尺度解讀要小心。",
                 "The outcome is not very rare — interpret the scale of the estimate with care.")
    else:
        status = "red"
        head = t(lang, "結果太常見，trend-in-trend 的罕見近似可能失效。",
                 "The outcome is too common — the rare-outcome approximation may fail.")
    return {
        "id": "A2",
        "title": t(lang, "結果夠罕見嗎？", "Is the outcome rare enough?"),
        "status": status, "headline": head,
        "plain": t(
            lang,
            "trend-in-trend 的概似建立在『結果是罕見事件』的近似上（這時勝算比和相對風險很接近、"
            "數學會簡化）。如果結果其實很常見，這層近似就不夠好，估計尺度的解讀要更謹慎。",
            "The trend-in-trend likelihood is built on a rare-outcome approximation (then the odds ratio and the "
            "risk ratio nearly coincide and the maths simplifies). If the outcome is actually common, that "
            "approximation is shaky and the scale of the estimate needs more caution.",
        ),
        "term": t(lang, "專有名詞：罕見結果假設（rare-outcome assumption）。",
                  "Term: rare-outcome assumption."),
        "metrics": metrics,
    }


def _a3_covariate_trend(df, covariates, periods, lang="zh"):
    # do the (cell-mean) baseline covariates drift over calendar time?
    worst = 0.0
    rows = []
    for c in covariates:
        means = np.array([float(df.loc[df["period"] == tp, c].mean()) for tp in periods])
        sd = float(df[c].std()) + 1e-9
        drift = abs(means[-1] - means[0]) / sd      # standardized drift
        worst = max(worst, drift)
        rows.append({"name": t(lang, f"共變項隨時間漂移：{c}", f"Covariate drift over time: {c}"),
                     "value": round(drift, 3),
                     "note": t(lang, "接近 0 代表沒有隨時間漂", "near 0 means no drift over time")})
    if worst < 0.15:
        status = "green"
        head = t(lang, "基線特徵不隨日曆時間漂移，符合假設。",
                 "Baseline characteristics do not drift over calendar time — assumption met.")
    elif worst < 0.35:
        status = "amber"
        head = t(lang, "有些特徵隨時間略有漂移，要留意是否與暴露趨勢混在一起。",
                 "Some characteristics drift a little over time — watch for confounding with the exposure trend.")
    else:
        status = "red"
        head = t(lang, "特徵隨時間明顯漂移，可能與暴露趨勢糾纏，估計要保守看。",
                 "Characteristics drift clearly over time — possibly entangled with the exposure trend; interpret with caution.")
    return {
        "id": "A3",
        "title": t(lang, "可測的背景特徵不隨時間漂移嗎？", "Do measured characteristics stay stable over time?"),
        "status": status, "headline": head,
        "plain": t(
            lang,
            "trend-in-trend 假設『背景特徵不隨日曆時間系統性改變』（或就算變也與暴露趨勢無關）。"
            "如果隨著時間，使用者的年齡、疾病組成等悄悄改變，而且剛好跟暴露上升同步，就會混淆估計。"
            "我們檢查可測特徵在各時間點的平均有沒有漂移；看不見的特徵則屬於 A4。",
            "Trend-in-trend assumes measured characteristics do not change systematically over calendar time "
            "(or that any change is unrelated to the exposure trend). If, over time, the case mix quietly shifts in step "
            "with rising exposure, it confounds the estimate. We check whether measured covariates drift across periods; "
            "unmeasured ones fall under A4.",
        ),
        "term": t(lang, "專有名詞：共變項的時間穩定性（temporal stability of covariates）。",
                  "Term: temporal stability of covariates."),
        "metrics": rows,
    }


def _a4_confounder_trend(lang="zh"):
    return {
        "id": "A4",
        "title": t(lang, "有沒有『跟著暴露一起隨時間變』的看不見因素？（關鍵、不可檢驗）",
                   "Any unmeasured factor that trends WITH exposure over time? (key, untestable)"),
        "status": "info",
        "headline": t(lang, "這是 trend-in-trend 最關鍵的假設，無法用資料證明，要靠領域知識。",
                      "This is trend-in-trend's key assumption; it cannot be proven from data and rests on domain knowledge."),
        "plain": t(
            lang,
            "trend-in-trend 不怕『固定不動的混淆』——那會被 CPE 分層與層別基線吸收掉。它真正怕的是"
            "『一個看不見的因素，剛好也隨日曆時間變化，而且這個變化在不同 CPE 層之間，與暴露的上升趨勢相關』。"
            "例如：診斷標準逐年改變、整體醫療行為的時代變遷，若剛好和用藥潮同步又跨層不一致，就會假裝成因果。"
            "好消息：會破壞 trend-in-trend 的情境，是會破壞傳統世代研究情境的『子集』——所以它比世代研究更穩；"
            "壞消息：仍需用領域知識論證沒有這種『與暴露趨勢同步的時代變化』。",
            "Trend-in-trend is NOT troubled by fixed confounding — that is absorbed by CPE stratification and the "
            "stratum baselines. What it truly fears is an unmeasured factor that ALSO changes over calendar time, with "
            "that change correlated with the exposure trend ACROSS strata. For instance: diagnostic criteria drifting "
            "year by year, or secular shifts in practice, if they happen to move in step with the uptake wave and "
            "differently across strata, can masquerade as causation. The good news: the scenarios that break "
            "trend-in-trend are a SUBSET of those that break an ordinary cohort study — so it is more robust; the bad "
            "news: you still need domain knowledge to argue no such exposure-synchronised secular change exists.",
        ),
        "term": t(lang, "專有名詞：與暴露趨勢相關的未測混淆趨勢（unmeasured confounder trends correlated with the exposure trend across strata）。",
                  "Term: unmeasured confounder trends correlated with the exposure trend across strata."),
        "metrics": [],
    }


def _a5_multiplicative(auc, lang="zh"):
    metrics = [
        {"name": t(lang, "CPE 模型區辨力（c 統計量／AUC）", "CPE model discrimination (c-statistic / AUC)"),
         "value": round(auc, 3) if np.isfinite(auc) else None,
         "note": t(lang, "越高代表分層越能拉開暴露趨勢差異",
                   "higher means the strata separate the exposure trends better")},
    ]
    if np.isfinite(auc) and auc >= 0.70:
        status = "green"
        head = t(lang, "CPE 模型能有效把人分到暴露趨勢不同的層，分層基礎良好。",
                 "The CPE model separates people into strata with distinct exposure trends — a good basis.")
    elif np.isfinite(auc) and auc >= 0.60:
        status = "amber"
        head = t(lang, "CPE 模型區辨力一般，分層帶來的趨勢差異有限，檢定力會受影響。",
                 "The CPE model is only moderately discriminating — limited trend separation and reduced power.")
    else:
        status = "info"
        head = t(lang, "CPE 模型區辨力偏低，建議加入更強的暴露預測因子。",
                 "Low CPE discrimination — consider adding stronger predictors of exposure.")
    return {
        "id": "A5",
        "title": t(lang, "分層與可乘結構站得住嗎？", "Do the stratification and multiplicative structure hold up?"),
        "status": status, "headline": head,
        "plain": t(
            lang,
            "trend-in-trend 先用基線特徵估每個人的『累積暴露機率（CPE）』再分層，並假設共變項對暴露的影響"
            "與時間是『可乘分離』的（covariate 效果不隨時間交互）。CPE 模型若能有力地預測誰會暴露，"
            "各層的暴露時間趨勢差異就拉得開、識別力更好。這裡用 c 統計量（AUC）當分層品質的指標。",
            "Trend-in-trend first estimates each person's cumulative probability of exposure (CPE) from baseline "
            "characteristics and stratifies on it, assuming covariate effects on exposure separate multiplicatively from "
            "time (no covariate-by-time interaction). The more strongly the CPE model predicts who gets exposed, the "
            "more the strata's exposure-time trends differ and the better the identification. We use the c-statistic "
            "(AUC) as a measure of stratification quality.",
        ),
        "term": t(lang, "專有名詞：累積暴露機率（CPE）分層、可乘共變項-時間結構（multiplicative covariate–time structure）、c 統計量。",
                  "Term: CPE stratification; multiplicative covariate–time structure; c-statistic."),
        "metrics": metrics,
    }

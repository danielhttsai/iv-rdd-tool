"""Sequential (nested) trials assumption checks C1–C5 — following Hernán & Robins
(target trial), Danaei et al., Gran et al. Core identifying assumptions are untestable
(blue info cards); positivity and having enough trials/events are checkable.

Each check returns {id, title, status, headline, plain, term, metrics:[...]};
run_dashboard returns {"checks": [...]}.
"""
from __future__ import annotations

import numpy as np

import seq_core
from i18n import t


def run_dashboard(df, init_time="init_month", event="event", futime="futime",
                  covariates=("age", "frailty"), n_trials=None, horizon=None, lang="zh"):
    res = seq_core.full_seq(df, init_time, event, futime, covariates, n_trials, horizon, lang=lang)
    init = np.asarray(df[init_time], dtype=float)
    ev = np.asarray(df[event], dtype=float)
    checks = [
        _c1_confounding(res, lang),
        _c2_positivity(df, init, covariates, res, lang),
        _c3_alignment(lang),
        _c4_carryover(lang),
        _c5_enough(res, ev, lang),
    ]
    return {"checks": checks}


def _c1_confounding(res, lang="zh"):
    metrics = [{"name": t(lang, "天真 vs 序列估計的差距", "Gap between naive and sequential"),
                "value": f"{res['naive']:+.2f} vs {res['seq_rd']:+.2f}",
                "note": t(lang, "差距大＝immortal-time／混淆的校正幅度大",
                          "a large gap means a large correction for immortal time / confounding")}]
    return {
        "id": "C1",
        "title": t(lang, "每個資格時點都無未測混淆嗎？（關鍵、不可檢驗）",
                   "No unmeasured confounding at each eligibility time? (key, untestable)"),
        "status": "info",
        "headline": t(lang, "每場 mini-trial 內，『當下啟動 vs 不啟動』只由可測共變項決定；這要靠領域知識與設計。",
                      "Within each mini-trial, initiating-now vs not must be governed only by measured covariates — ensured by domain knowledge and design."),
        "plain": t(
            lang,
            "序列試驗把每個資格月當成一場隨機化模擬：在那一刻，啟動與不啟動的人，必須在所有會影響結果的"
            "因素上可比（給定基線共變項）。我們用年齡、體弱程度做 IPTW；但若還有<b>沒測到</b>的因素同時影響"
            "『是否在此刻啟動』與『結果』，估計仍會有偏。做法：盡量納入重要共變項、做未測混淆敏感度分析。",
            "Sequential trials treat each eligibility month as a randomization emulation: at that moment, initiators and "
            "non-initiators must be comparable on everything affecting the outcome (given baseline covariates). We IPTW "
            "on age and frailty; but an <b>unmeasured</b> factor driving both 'initiate now?' and the outcome still "
            "biases the estimate. Remedy: include the important confounders and run an unmeasured-confounding sensitivity "
            "analysis.",
        ),
        "term": t(lang, "專有名詞：（序列性）可交換性；目標試驗模擬（target trial emulation）。",
                  "Term: (sequential) exchangeability; target trial emulation."),
        "metrics": metrics,
    }


def _c2_positivity(df, init, covariates, res, lang="zh"):
    # pooled positivity: in covariate strata, do both initiate and not-initiate occur
    early = (~np.isnan(init)) & (init <= 1)     # initiated very early (a rough "treated soon" proxy)
    worst = 1.0; rows = []
    for c in covariates:
        v = np.asarray(df[c], dtype=float)
        uniq = np.unique(v)
        groups = ([(f"{c}={int(u)}", v == u) for u in uniq] if uniq.size <= 2
                  else [(f"{c}≤median", v <= np.median(v)), (f"{c}>median", v > np.median(v))])
        for nm, m in groups:
            if m.sum() == 0:
                continue
            sh = float(early[m].mean()); worst = min(worst, sh, 1 - sh); rows.append((nm, sh))
    metrics = [{"name": t(lang, f"早啟動比例（{nm}）", f"Early-initiation share ({nm})"),
                "value": f"{sh*100:.0f}%",
                "note": t(lang, "太接近 0%／100% → 該層幾乎只有一種選擇（違反正性）",
                          "near 0%/100% means that stratum almost only does one thing (positivity violation)")}
               for nm, sh in rows]
    if worst >= 0.10:
        status, head = "green", t(lang, "每個共變項層裡，啟動與不啟動都有足夠的人——正性大致成立。",
                                  "Both initiating and not occur in every stratum — positivity holds.")
    elif worst >= 0.03:
        status, head = "amber", t(lang, "某些層裡一種選擇偏少——權重偏大、估計較不穩。",
                                  "Some strata are sparse on one choice — weights get large and the estimate is less stable.")
    else:
        status, head = "red", t(lang, "某些層幾乎只走一種選擇（近乎違反正性）。",
                                "Some strata almost only do one thing (near positivity violation).")
    return {
        "id": "C2", "title": t(lang, "正性：每種人在每個時點都可能啟動或不啟動嗎？（可檢驗）",
                               "Positivity: could every kind of person initiate or not at each time? (testable)"),
        "status": status, "headline": head,
        "plain": t(
            lang,
            "每場 mini-trial 的 IPTW 要成立，必須『不論共變項長相，當下啟動與不啟動的機率都大於 0』。若某種人"
            "（例如最體弱者）幾乎一定會啟動，那一層就沒有可比的對照，權重會爆大。",
            "The IPTW in each mini-trial requires that, whatever the covariates, the probability of initiating-now and of "
            "not is above 0. If some people (say the frailest) almost always initiate, that stratum has no comparable "
            "controls and the weights blow up.",
        ),
        "term": t(lang, "專有名詞：正性（positivity）；傾向加權（IPTW）。", "Term: positivity; inverse-probability-of-treatment weighting."),
        "metrics": metrics,
    }


def _c3_alignment(lang="zh"):
    return {
        "id": "C3",
        "title": t(lang, "時間零點、資格、指派有對齊嗎？（靠設計）",
                   "Are time-zero, eligibility and assignment aligned? (by design)"),
        "status": "info",
        "headline": t(lang, "每場 mini-trial 的時間零點＝該資格月；資格、基線共變項、治療指派都在那一刻對齊，才能消除 immortal time。",
                      "Each mini-trial's time-zero is its eligibility month; eligibility, baseline covariates and assignment are aligned there — that is what removes immortal time."),
        "plain": t(
            lang,
            "immortal-time bias 來自『用未來資訊（最後有沒有治療）回頭分組』。序列試驗的解法是：在每個資格月把"
            "時間零點固定下來，當下比較啟動 vs 不啟動，基線共變項也在那一刻測量。只要這三者（時間零點、資格、"
            "指派）對齊，immortal time 就被消除。",
            "Immortal-time bias comes from grouping with future information (whether someone was ever treated). Sequential "
            "trials fix it by fixing time-zero at each eligibility month, comparing initiate-vs-not at that moment with "
            "baseline covariates measured then. Aligning time-zero, eligibility and assignment removes immortal time.",
        ),
        "term": t(lang, "專有名詞：immortal-time bias；時間零點對齊；巢式序列試驗。",
                  "Term: immortal-time bias; time-zero alignment; nested sequential trials."),
        "metrics": [],
    }


def _c4_carryover(lang="zh"):
    return {
        "id": "C4",
        "title": t(lang, "巢式試驗之間有沒有 carry-over？（重複收案的相關性）",
                   "Carry-over between nested trials? (dependence from repeated entry)"),
        "status": "info",
        "headline": t(lang, "同一人在多場 trial 以『未啟動』重複出現，這些列彼此相關；標準誤要用個人叢集（自助）處理。",
                      "A person re-enters several trials as a non-initiator; those rows are correlated — use person-clustered (bootstrap) standard errors."),
        "plain": t(
            lang,
            "序列試驗的威力之一是『同一個人可在多個資格月被重複納入』，放大有效樣本。但這也代表這些列<b>不是獨立的</b>，"
            "天真的標準誤會太窄。正確做法是用<b>個人叢集</b>的穩健標準誤（或對 pid 自助重抽），本工具的信賴區間"
            "即可選用個人叢集自助。",
            "A strength of sequential trials is that a person can re-enter at several eligibility months, boosting the "
            "effective sample. But those rows are <b>not independent</b>, so naive standard errors are too narrow. The "
            "fix is <b>person-clustered</b> robust SEs (or bootstrapping by pid); this tool can use a person-cluster "
            "bootstrap for the interval.",
        ),
        "term": t(lang, "專有名詞：carry-over；個人叢集標準誤（person-clustered SE）。",
                  "Term: carry-over; person-clustered standard errors."),
        "metrics": [],
    }


def _c5_enough(res, ev, lang="zh"):
    ntr = res["n_trials"]
    nmin = int(min((p["n_init"] for p in res["per_trial"]), default=0))
    nev = int(np.sum(ev > 0))
    metrics = [
        {"name": t(lang, "可用的巢式試驗數", "Usable nested trials"), "value": ntr,
         "note": t(lang, "越多資格時點＝越多可合併的試驗", "more eligibility times = more trials to pool")},
        {"name": t(lang, "最少的單場啟動人數", "Fewest initiators in a trial"), "value": nmin,
         "note": t(lang, "太少→該場風險差很不穩", "too few → that trial's risk difference is unstable")},
        {"name": t(lang, "總事件數", "Total events"), "value": nev, "note": ""},
    ]
    if ntr >= 3 and nmin >= 30:
        status, head = "green", t(lang, "試驗數與單場人數都足夠，合併估計穩定。",
                                  "Enough trials and initiators per trial — the pooled estimate is stable.")
    elif ntr >= 2 and nmin >= 10:
        status, head = "amber", t(lang, "試驗數或單場人數偏少，合併估計較不穩。",
                                  "Few trials or initiators — the pooled estimate is less stable.")
    else:
        status, head = "red", t(lang, "可用試驗或事件太少，序列估計不可靠。",
                                "Too few usable trials or events — the sequential estimate is unreliable.")
    return {
        "id": "C5", "title": t(lang, "巢式試驗與事件數夠多嗎？（可檢驗）",
                               "Enough nested trials and events? (testable)"),
        "status": status, "headline": head,
        "plain": t(
            lang,
            "序列估計合併多場 mini-trial。如果可用的資格時點很少、或某些場的啟動人數很少，合併後的風險差就估得"
            "不穩、區間變寬。延長收案窗、選事件較常見的結果都有幫助。",
            "The sequential estimate pools several mini-trials. If there are few eligibility times, or some trials have "
            "few initiators, the pooled risk difference is unstable and the interval widens. A longer recruitment window "
            "or a more common outcome both help.",
        ),
        "term": t(lang, "專有名詞：巢式試驗數／事件數（trials & events）；反變異合併。",
                  "Term: number of trials & events; inverse-variance pooling."),
        "metrics": metrics,
    }

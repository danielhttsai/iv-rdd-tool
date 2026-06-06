"""ACNU assumption checks C1–C5. The identifying assumptions are mostly about study
DESIGN (active comparator + new users) and are untestable from data alone (blue info
cards); the testable ones are the residual severity imbalance between A and B and whether
there are enough events.

Each check returns {id, title, status, headline, plain, term, metrics:[...]};
run_dashboard returns {"checks": [...]}.
"""
from __future__ import annotations

import numpy as np

import acnu_core
from i18n import t


def run_dashboard(df, drug="drug", event="event", futime="futime", lang="zh"):
    res = acnu_core.full_acnu(df, drug=drug, event=event, futime=futime, lang=lang)
    checks = [
        _c1_comparator(lang),
        _c2_newuser(lang),
        _c3_comparator_effect(lang),
        _c4_residual(res, lang),
        _c5_events(res, lang),
    ]
    return {"checks": checks}


def _c1_comparator(lang="zh"):
    return {
        "id": "C1",
        "title": t(lang, "對照藥和 A 治療『同一個適應症』嗎？（可交換性的來源，關鍵、不可檢驗）",
                   "Does the comparator treat the SAME indication as A? (the source of exchangeability — key, untestable)"),
        "status": "info",
        "headline": t(lang, "ACNU 靠『主動對照藥同適應症』讓兩組病人在病情上可比；選錯對照藥，混淆就回來了。",
                      "ACNU relies on the active comparator sharing the indication so the two groups are comparable in disease; pick the wrong comparator and confounding returns."),
        "plain": t(
            lang,
            "ACNU 之所以能削掉<b>因適應症而生的混淆</b>，關鍵在於對照藥 B 和研究藥 A <b>治療同一個適應症</b>、"
            "面對的是<b>病情相似</b>的病人。這樣『誰拿 A、誰拿 B』比較像在同一群病人裡的選擇，而不是『有病 vs 沒病』。"
            "如果 B 其實用在較輕（或較重）的病人，兩組基線風險就不同，ACNU 的好處會打折。這要靠<b>臨床知識</b>挑對照藥，"
            "資料本身證明不了。",
            "ACNU removes <b>confounding by indication</b> precisely because the comparator drug B treats the <b>same "
            "indication</b> as the study drug A and is given to <b>clinically similar</b> patients. Then 'who gets A vs B' is "
            "more like a choice within one patient population than 'diseased vs not'. If B is actually used in milder (or more "
            "severe) patients, the two groups differ in baseline risk and ACNU's benefit shrinks. Choosing the right comparator "
            "is a matter of <b>clinical knowledge</b>; the data cannot prove it.",
        ),
        "term": t(lang, "專有名詞：主動對照（active comparator）；因適應症而生的混淆（confounding by indication）；可交換性。",
                  "Term: active comparator; confounding by indication; exchangeability."),
        "metrics": [],
    }


def _c2_newuser(lang="zh"):
    return {
        "id": "C2",
        "title": t(lang, "兩組都是『新使用者』、時間零點對齊嗎？（避免 immortal-time／既有使用者偏誤）",
                   "Are both groups NEW users with an aligned time zero? (avoid immortal-time / prevalent-user bias)"),
        "status": "info",
        "headline": t(lang, "新使用者設計把『第一張處方』當時間零點，兩組同時起跑——避免納入既有使用者帶來的存活者偏誤。",
                      "The new-user design sets time zero at the first prescription so both groups start together — avoiding the survivor bias of including prevalent users."),
        "plain": t(
            lang,
            "如果把<b>既有使用者</b>（已經用了一段時間的人）也算進來，他們是『用了還沒出事、所以還在用』的存活者——"
            "天生就比較健康（depletion of susceptibles），會讓藥看起來比實際安全，這就是 prevalent-user 偏誤。"
            "ACNU 只收<b>新使用者</b>，把每個人的<b>第一張處方</b>當時間零點，兩組同時起跑、同樣從零開始累積風險，"
            "也就不會有 immortal time。要做到這點，資料必須看得到完整的用藥起始史。",
            "Including <b>prevalent users</b> (already on the drug for a while) means counting survivors — people who tolerated "
            "the drug and are therefore healthier (depletion of susceptibles) — which makes the drug look safer than it is "
            "(prevalent-user bias). ACNU enrols only <b>new users</b> and sets time zero at each person's <b>first "
            "prescription</b>, so both groups start together and accrue risk from zero, with no immortal time. This requires "
            "the data to capture the full treatment-initiation history.",
        ),
        "term": t(lang, "專有名詞：新使用者設計（new-user design）；既有使用者偏誤；immortal time；易感者耗竭。",
                  "Term: new-user design; prevalent-user bias; immortal time; depletion of susceptibles."),
        "metrics": [],
    }


def _c3_comparator_effect(lang="zh"):
    return {
        "id": "C3",
        "title": t(lang, "對照藥 B 本身對這個結果『沒有（或已知的）效應』嗎？（可檢驗性有限）",
                   "Does comparator B itself have no (or a known) effect on this outcome? (limited testability)"),
        "status": "info",
        "headline": t(lang, "ACNU 估的是 A『相對 B』的效應；若 B 也會影響結果，估出來的是兩者之差，要小心解讀。",
                      "ACNU estimates A's effect RELATIVE to B; if B also affects the outcome, the estimate is their difference — interpret with care."),
        "plain": t(
            lang,
            "用主動對照的代價是：你估的是 A <b>相對於 B</b> 的效應，不是 A 相對於『什麼都不做』。如果對照藥 B 對這個結果"
            "<b>本身就有保護或有害的效應</b>，那 ACNU 的速率比就被 B 的效應汙染了。最理想的對照藥是『對該結果中性、"
            "但治療同適應症』的藥；否則要用外部知識把 B 的效應納入解讀。",
            "The price of an active comparator is that you estimate A's effect <b>relative to B</b>, not relative to 'doing "
            "nothing'. If comparator B has its <b>own protective or harmful effect</b> on this outcome, the ACNU rate ratio is "
            "contaminated by B's effect. The ideal comparator is a drug that is <b>neutral for this outcome</b> while treating "
            "the same indication; otherwise B's effect must be folded into the interpretation using external knowledge.",
        ),
        "term": t(lang, "專有名詞：主動對照的效應；相對效應；陰性對照結果（negative-control outcome）。",
                  "Term: comparator effect; relative effect; negative-control outcome."),
        "metrics": [],
    }


def _c4_residual(res, lang="zh"):
    bal = res.get("severity_balance") or {}
    gap_AB = abs(bal.get("A", 0.0) - bal.get("B", 0.0))
    gap_An = abs(bal.get("A", 0.0) - bal.get("none", 0.0))
    metrics = [
        {"name": t(lang, "嚴重度差：A vs 對照藥 B", "Severity gap: A vs comparator B"),
         "value": f"{gap_AB:.2f}",
         "note": t(lang, "限制在新使用者＋主動對照後，殘留的嚴重度差（越小越好）",
                   "the residual severity gap after restricting to new users + active comparator (smaller is better)")},
        {"name": t(lang, "嚴重度差：A vs 沒用藥（對比）", "Severity gap: A vs non-users (for contrast)"),
         "value": f"{gap_An:.2f}",
         "note": t(lang, "天真對照的嚴重度差——通常大得多，這就是天真比較偏很多的原因",
                   "the naive contrast's gap — usually much larger, which is why the naive comparison is so biased")},
        {"name": t(lang, "粗 ACNU → 校正後", "crude ACNU → adjusted"),
         "value": f"{res['crude_irr']:.2f} → {res['adj_irr']:.2f}",
         "note": t(lang, "校正把殘留嚴重度混淆補掉，移向真值", "adjustment removes residual severity confounding, moving toward truth")},
    ]
    if gap_AB < 0.3:
        status = "green"
        head = t(lang, "A 與對照藥 B 的嚴重度已很接近——殘留混淆小，校正只是微調。",
                 "A and comparator B are already close in severity — little residual confounding; adjustment is a fine-tune.")
    elif gap_AB < 0.9:
        status = "amber"
        head = t(lang, "A 與 B 仍有殘留的嚴重度差——主動對照削掉了大半混淆，剩下的要靠傾向分數／共變項校正補掉。",
                 "A and B still differ somewhat in severity — the active comparator removed most confounding; adjust the rest with a propensity score / covariates.")
    else:
        status = "red"
        head = t(lang, "A 與 B 的嚴重度差很大——對照藥可能不夠相似，或有未測的嚴重度，殘留混淆風險高。",
                 "A and B differ a lot in severity — the comparator may not be similar enough, or severity is unmeasured; high residual-confounding risk.")
    return {
        "id": "C4",
        "title": t(lang, "殘留混淆校正掉了嗎？（可檢驗：A vs B 的嚴重度平衡）",
                   "Is residual confounding adjusted? (testable: severity balance A vs B)"),
        "status": status, "headline": head,
        "plain": t(
            lang,
            "主動對照＋新使用者把<b>大部分</b>因適應症的混淆削掉，但 A 與 B 之間通常還有<b>殘留</b>的嚴重度差"
            "（這裡 A vs B 的差比 A vs 沒用藥小很多）。把這個殘留用<b>傾向分數或共變項校正</b>補掉，速率比就會從"
            "粗估移向真值。上面三個指標就是在看：殘留差有多大、天真對照差多大、校正前後差多少。",
            "The active comparator + new-user design removes <b>most</b> confounding by indication, but A and B usually still "
            "differ a little in severity (here the A-vs-B gap is much smaller than A-vs-non-users). Mopping up that residual "
            "with a <b>propensity score or covariate adjustment</b> moves the rate ratio from the crude estimate toward the "
            "truth. The three metrics above show how large the residual gap is, how large the naive gap is, and how much "
            "adjustment moves the estimate.",
        ),
        "term": t(lang, "專有名詞：殘留混淆；傾向分數（propensity score）；標準化差（standardized difference）。",
                  "Term: residual confounding; propensity score; standardized difference."),
        "metrics": metrics,
    }


def _c5_events(res, lang="zh"):
    ev = res.get("events") or {}
    eA, eB = int(ev.get("A", 0)), int(ev.get("B", 0))
    mn = min(eA, eB)
    metrics = [
        {"name": t(lang, "事件數（A／對照藥 B）", "Events (A / comparator B)"), "value": f"{eA} / {eB}",
         "note": t(lang, "兩臂都要有夠多事件，速率比才穩", "both arms need enough events for a stable rate ratio")},
        {"name": t(lang, "新使用者數（A／B）", "New users (A / B)"),
         "value": f"{res['n_a']} / {res['n_b']}",
         "note": t(lang, "主動對照組越大，估計越精確", "a larger comparator arm gives a more precise estimate")},
    ]
    if mn >= 200:
        status, head = "green", t(lang, "兩臂事件都很充足——速率比與信賴區間穩定。",
                                  "Plenty of events in both arms — the rate ratio and CI are stable.")
    elif mn >= 50:
        status, head = "amber", t(lang, "事件數中等——信賴區間會偏寬，解讀留意精確度。",
                                  "Moderate event counts — the CI will be wide; mind the precision.")
    else:
        status, head = "red", t(lang, "事件太少——速率比很不穩，別過度解讀。",
                                "Too few events — the rate ratio is unstable; don't over-interpret.")
    return {
        "id": "C5",
        "title": t(lang, "事件數夠嗎？（可檢驗）", "Are there enough events? (testable)"),
        "status": status, "headline": head,
        "plain": t(
            lang,
            "ACNU 的速率比由各臂的<b>事件數</b>決定精確度。主動對照雖然削掉偏誤，但因為只比『用 A vs 用 B』、"
            "捨棄了沒用藥的人，<b>樣本與事件數會比天真比較少</b>。事件太少時，信賴區間會很寬，要小心別把雜訊當訊號。",
            "The precision of the ACNU rate ratio is driven by the <b>event counts</b> in each arm. The active comparator "
            "removes bias, but because it compares only 'A vs B' and discards non-users, the <b>sample and event counts are "
            "smaller</b> than in the naive comparison. With few events the CI is wide — be careful not to read noise as signal.",
        ),
        "term": t(lang, "專有名詞：人時（person-time）；事件率；精確度／效能。",
                  "Term: person-time; event rate; precision / power."),
        "metrics": metrics,
    }

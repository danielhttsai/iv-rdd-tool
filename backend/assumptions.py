"""IV assumption checks A1-A4b — port of the framework in Homayra et al. 2024.

Design principle for the text: **白話文優先**。每一項先用日常語言說明我們在檢查什麼、
結果代表什麼,專有名詞一律放到最後的 `term` 欄位,並附上白話的專業解釋。

Each check returns:
    {
        "id": "A1",
        "title":   "<白話標題>",
        "status":  "green" | "amber" | "red" | "info",
        "headline":"<一句白話結論>",
        "plain":   "<我們在檢查什麼、為什麼重要,全用白話>",
        "term":    "<最後才出現的專有名詞 + 白話解釋>",
        "metrics": [{"name": "<白話名稱>", "value": ..., "note": "<可含術語>"}],
    }
"""
from __future__ import annotations

import numpy as np

import iv_core


def _binary(series) -> bool:
    vals = set(np.unique(np.asarray(series)))
    return vals.issubset({0, 1})


# ---------------------------------------------------------------------------
# A1 — Instrument strength (relevance)
# ---------------------------------------------------------------------------
def check_a1_strength(df, A, Z):
    fs = iv_core.first_stage(df, A, Z)
    f = fs["f_stat"]
    pct = fs["coef"] * 100
    metrics = [
        {"name": "有多少人被這個外力推動", "value": f"約 {pct:.1f}%",
         "note": "被推動而改變行為的人(complier)的比例"},
        {"name": "外力夠不夠力的分數", "value": round(f, 1),
         "note": "統計上叫「第一階段 F 統計量」,大於 10 算夠力"},
    ]
    if _binary(df[A]):
        mcf = _mcfadden_r2(df, A, Z)
        metrics.append({"name": "外力對「要不要做」的解釋力", "value": round(mcf, 4),
                        "note": "統計上叫 McFadden 偽 R²"})
    if f >= 10:
        status = "green"
        head = "這個外力夠力,有推動足夠多人改變,後面的分析可以放心做。"
    elif f >= 5:
        status = "amber"
        head = "這個外力有點弱,推動的人不夠多,結果要保守看待。"
    else:
        status = "red"
        head = "這個外力太弱了,幾乎沒推動什麼人,算出來的結果很可能不可靠。"
    return {
        "id": "A1",
        "title": "A1・這個「外力」夠不夠力?",
        "status": status, "headline": head,
        "plain": ("工具變數法靠一個「外力」(這裡是有沒有收到政府的免費疫苗券)去推動人們改變行為。"
                  "如果這個外力其實幾乎沒推動任何人,那我們等於拿一個沒作用的東西在做推論,"
                  "算出來的因果效應就會非常不穩定、忽大忽小。所以第一步要確認:"
                  "這個外力真的有讓夠多人去接種嗎?"),
        "term": ("📖 專有名詞:這一步在檢查工具的「相關性 / 強度」。常用「第一階段 F 統計量」當分數,"
                 "經驗法則是大於 10 就算夠強、低於 10 稱為「弱工具(weak instrument)」。"
                 "當處置是「有/沒有」這種二元時,也可看 McFadden 偽 R²,代表外力對行為的解釋力。"),
        "metrics": metrics,
    }


def _mcfadden_r2(df, A, Z):
    y = np.asarray(df[A], dtype=float)
    X = np.column_stack([np.ones(len(df)), np.asarray(df[Z], dtype=float)])
    beta = np.zeros(X.shape[1])
    for _ in range(50):
        eta = X @ beta
        p = 1 / (1 + np.exp(-eta))
        W = p * (1 - p)
        grad = X.T @ (y - p)
        H = X.T @ (X * W[:, None])
        try:
            step = np.linalg.solve(H, grad)
        except np.linalg.LinAlgError:
            break
        beta += step
        if np.max(np.abs(step)) < 1e-8:
            break
    eta = X @ beta
    p = np.clip(1 / (1 + np.exp(-eta)), 1e-9, 1 - 1e-9)
    ll = np.sum(y * np.log(p) + (1 - y) * np.log(1 - p))
    pbar = np.clip(y.mean(), 1e-9, 1 - 1e-9)
    ll0 = np.sum(y * np.log(pbar) + (1 - y) * np.log(1 - pbar))
    return float(1 - ll / ll0) if ll0 != 0 else float("nan")


# ---------------------------------------------------------------------------
# A2 — Exclusion restriction (not statistically testable)
# ---------------------------------------------------------------------------
def check_a2_exclusion(df, Y, A, Z):
    return {
        "id": "A2",
        "title": "A2・這個外力是不是只走「一條路」?",
        "status": "info",
        "headline": "這題資料算不出來,要靠你對這個領域的了解來判斷。",
        "plain": ("我們需要這個外力(免費疫苗券)『只透過』讓人去接種疫苗,來影響健康;"
                  "不能還偷偷走別條路。舉例來說,如果收到疫苗券的地區剛好同時加發了健康補助、"
                  "或醫療資源也比較多,那健康變好就不全是疫苗的功勞——外力走了別條路,結論就會被汙染。"
                  "麻煩的是:這件事沒辦法用手上的資料直接驗證,必須靠常識和專業知識去論證,"
                  "確認這個外力真的沒有別的影響途徑。"),
        "term": ("📖 專有名詞:這個假設叫「排除限制(exclusion restriction)」。"
                 "因為無法用統計檢定,實務上的輔助做法是:找一個理論上『不該被外力影響』的結果當"
                 "「負對照(negative control)」來檢查;或做「敏感度分析」,評估萬一假設稍微被違反、結論會不會翻盤。"),
        "metrics": [
            {"name": "能不能用資料證明?", "value": "不能", "note": "要靠專業判斷"},
            {"name": "建議的輔助做法", "value": "負對照 / 敏感度分析", "note": "間接佐證"},
        ],
    }


# ---------------------------------------------------------------------------
# A3 — Independence / exchangeability (instrument vs covariates balance)
# ---------------------------------------------------------------------------
def check_a3_independence(df, Z, covariates):
    rows = []
    max_smd = 0.0
    for c in covariates:
        x = np.asarray(df[c], dtype=float)
        g1 = x[np.asarray(df[Z]) == 1]
        g0 = x[np.asarray(df[Z]) == 0]
        if len(g1) == 0 or len(g0) == 0:
            continue
        pooled_sd = np.sqrt((g1.var(ddof=1) + g0.var(ddof=1)) / 2)
        smd = abs(g1.mean() - g0.mean()) / pooled_sd if pooled_sd > 0 else 0.0
        max_smd = max(max_smd, smd)
        rows.append({
            "name": c,
            "value": round(smd, 3),
            "note": f"有外力組均值 {g1.mean():.2f} / 沒有組 {g0.mean():.2f}（差距越小越好）",
        })
    if max_smd < 0.1:
        status = "green"
        head = "有外力和沒外力的兩群人,其他條件都很接近,看起來像隨機分配,很好。"
    elif max_smd < 0.2:
        status = "amber"
        head = "兩群人有些條件不太一樣,要留意這個外力可能不是完全隨機。"
    else:
        status = "red"
        head = "兩群人有明顯差異,這個外力恐怕不像隨機分配,結果要小心。"
    return {
        "id": "A3",
        "title": "A3・有外力 vs 沒外力的兩群人,長得像嗎?",
        "status": status, "headline": head,
        "plain": ("一個好的外力,應該像『抽籤』一樣決定誰收到疫苗券、誰沒有。如果真的像抽籤,"
                  "那收到券和沒收到券的兩群人,除了那張券之外,其他條件(年齡、BMI、收入…)"
                  "應該都差不多。我們就把這兩群人的各項特徵拿來比一比:如果處處都很接近,"
                  "代表這個外力比較可信;如果某些特徵差很多,就要懷疑它其實不是隨機的。"),
        "term": ("📖 專有名詞:這一步在檢查工具的「獨立性 / 可交換性(independence / exchangeability)」。"
                 "比較兩群人差異的數字叫「標準化均值差(SMD)」,通常小於 0.1 就算夠接近。"
                 "提醒:這只能比『有量到』的特徵,沒量到的干擾因子無法保證也平衡。"),
        "metrics": rows or [{"name": "(沒有選共變項)", "value": "-", "note": "請在分析頁選一些共變項"}],
    }


# ---------------------------------------------------------------------------
# A4a — Monotonicity (no defiers)
# ---------------------------------------------------------------------------
def check_a4a_monotonicity(df, A, Z):
    fs = iv_core.first_stage(df, A, Z)
    share = fs["coef"]
    if not _binary(df[A]) or not _binary(df[Z]):
        status = "info"
        head = "處置或外力不是「有/沒有」這種二元,這題只能粗略近似,請保守看待。"
    elif share > 0:
        status = "green"
        head = "大家被推動的方向一致(有外力的人確實更會去做),沒看到唱反調的跡象,很好。"
    else:
        status = "red"
        head = "整體方向是反的,可能有人「唱反調」,這會讓結果不可靠。"
    return {
        "id": "A4a",
        "title": "A4a・有沒有人「唱反調」?",
        "status": status, "headline": head,
        "plain": ("我們假設這個外力對每個人的推力方向都一樣——沒有人會『因為收到了疫苗券,"
                  "反而更不去接種』。這種專門唱反調的人如果存在,就會把結果攪亂。"
                  "問題是這種人沒辦法直接認出來,所以我們退而求其次:看整體的推動方向是不是一致地"
                  "『有外力→更會做這件事』,沒有反過來。"),
        "term": ("📖 專有名詞:這個假設叫「單調性(monotonicity)」,唱反調的人叫「defier」。"
                 "因為 defier 看不到,只能用第一階段的方向是否一致為正來間接判斷,"
                 "並在不同次群組中確認方向不會反轉。"),
        "metrics": [
            {"name": "被推動的人佔比", "value": f"約 {share*100:.1f}%", "note": "第一階段係數"},
            {"name": "整體推動方向", "value": "一致(正向)" if share > 0 else "相反(負向)",
             "note": "應該要一致正向"},
        ],
    }


# ---------------------------------------------------------------------------
# A4b — Homogeneity (effect stability — change-in-estimate)
# ---------------------------------------------------------------------------
def check_a4b_homogeneity(df, Y, A, Z, covariates):
    iv0 = iv_core.iv_2sls(df, Y, A, Z)["estimate"]
    if covariates:
        iv1 = iv_core.iv_2sls(df, Y, A, Z, covariates)["estimate"]
        denom = abs(iv0) if abs(iv0) > 1e-9 else 1.0
        change = abs(iv1 - iv0) / denom
        if change < 0.10:
            status = "green"
            head = "把其他條件考慮進來前後,答案幾乎沒變,效果看起來蠻穩定的。"
        elif change < 0.25:
            status = "amber"
            head = "把其他條件考慮進來後,答案有點變動,效果在不同人身上可能不太一樣。"
        else:
            status = "red"
            head = "把其他條件考慮進來後,答案變很多,效果在不同人身上差異可能很大。"
        metrics = [
            {"name": "原本的估計", "value": round(iv0, 3), "note": "沒加其他條件"},
            {"name": "考慮其他條件後", "value": round(iv1, 3), "note": "加入共變項"},
            {"name": "答案變動幅度", "value": f"{change*100:.1f}%", "note": "統計上叫 change-in-estimate"},
        ]
    else:
        status = "info"
        head = "還沒選其他條件(共變項),沒辦法做前後比較。"
        metrics = [{"name": "目前的估計", "value": round(iv0, 3), "note": "未加其他條件"}]
    return {
        "id": "A4b",
        "title": "A4b・這個效果對「每個人」都差不多嗎?",
        "status": status, "headline": head,
        "plain": ("接種疫苗對健康的好處,是不是對每個人都差不多?還是有些人受益很多、有些人幾乎沒用?"
                  "如果差很多,那我們算出來的數字其實只代表『被外力推動的那群人』,"
                  "不能隨便套到所有人身上。我們用一個粗略的方法檢查穩定度:把其他條件加進來算一次,"
                  "看答案有沒有跟著大幅變動——變動越小,代表效果越穩定。"),
        "term": ("📖 專有名詞:這個假設叫「效果同質性(homogeneity)」。IV 算出來的數字只代表"
                 "順從者那群人的效果,術語叫「LATE(局部平均處置效果)」。"
                 "這個加入共變項看答案變多少的檢查法,叫「change-in-estimate」。"),
        "metrics": metrics,
    }


def check_all(df, Y, A, Z, covariates=()):
    covariates = list(covariates)
    checks = [
        check_a1_strength(df, A, Z),
        check_a2_exclusion(df, Y, A, Z),
        check_a3_independence(df, Z, covariates),
        check_a4a_monotonicity(df, A, Z),
        check_a4b_homogeneity(df, Y, A, Z, covariates),
    ]
    order = {"red": 0, "amber": 1, "info": 2, "green": 3}
    worst = min((c["status"] for c in checks), key=lambda s: order[s])
    summary = {
        "green": "整體來說:能用資料檢查的項目都過關了。剩下「外力有沒有走別條路」這題,要再靠你的專業判斷。",
        "amber": "整體來說:有項目亮了黃燈,IV 的結論請保守一點看。",
        "red": "整體來說:有項目亮了紅燈,IV 的結論可能不可靠,要先處理問題。",
        "info": "整體來說:有些項目資料算不出來,需要你的專業判斷才能下結論。",
    }[worst]
    return {"checks": checks, "overall_status": worst, "overall_headline": summary}

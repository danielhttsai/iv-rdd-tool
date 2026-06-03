"""Generate the built-in DEMO dataset for the Trend-in-trend (TiT) tabs.

Fully fictional teaching scenario — NOT real data, NOT a copy of any source
dataset. We keep the same "does the exposure really change health?" spirit but
cast it as a NEW drug whose uptake rises over calendar time at different rates in
different parts of the population:

    情境：某新藥在 10 個季度間逐漸普及。用基線特徵算每個人的「累積暴露機率（CPE）」並分成
          5 層；採用率在高 CPE 層上升得快、低 CPE 層上升得慢（不同的時間趨勢）。看不見的
          干擾因子 U（例如體質／就醫傾向）同時推高『用藥』與『不良結果』——這會讓天真的
          世代比較高估，但 trend-in-trend 用『跨時間、跨層的盛行率關係』來識別真效果。
        個體     i，觀察於 t = 0..9（季）
        基線特徵 x1, x2          （決定 CPE）
        暴露     exposed         （當期是否用藥，二元，時間×層有不同趨勢）
        結果     outcome         （罕見不良事件，二元）
    真實因果勝算比 OR = 2.0（log OR = 0.693）。罕見結果（整體發生率 < 5%）。
"""
from __future__ import annotations

import os
import numpy as np
import pandas as pd

SEED = 91
N = 6000           # individuals
T = 10             # calendar periods (quarters)
K = 5              # CPE strata
TRUE_OR = 2.0      # true causal odds ratio of the exposure on the outcome

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "demo_tit.csv")

COLUMNS = ["pid", "period", "x1", "x2", "exposed", "outcome"]


def generate(n=N, t_periods=T, seed=SEED, trend=1.0):
    """trend scales how strongly exposure prevalence rises over calendar time
    (1.0 = the default strong trend; <1 = weaker trend → TiT loses power, wider CI —
    used by the ② interactive slider to teach assumption A1)."""
    rng = np.random.default_rng(seed)
    beta1 = np.log(TRUE_OR)

    # baseline covariates drive a latent propensity L = the cumulative probability of
    # exposure. People high on L take the drug sooner AND are sicker at baseline
    # (confounding by indication) — that is exactly what biases the naive comparison.
    x1 = rng.normal(0, 1, n)
    x2 = rng.binomial(1, 0.5, n).astype(float)
    L = 1.3 * x1 + 0.6 * x2 + rng.normal(0, 0.4, n)
    edges = np.quantile(L, np.linspace(0, 1, K + 1))
    edges[0] -= 1e-9
    stratum = np.clip(np.digitize(L, edges) - 1, 0, K - 1)  # 0..K-1 (true strata)
    # small residual within-stratum confounder for realism
    U = rng.standard_normal(n)

    expo_all = np.empty(n * t_periods, dtype=np.int8)
    out_all = np.empty(n * t_periods, dtype=np.int8)
    for t in range(t_periods):
        # exposure prevalence rises over calendar time, FASTER in higher strata
        # (the differential time trend that trend-in-trend exploits).
        slope = (0.05 + 0.12 * stratum) * float(trend)
        expo_logit = -4.0 + slope * t + 0.25 * U
        exposed = rng.binomial(1, 1.0 / (1.0 + np.exp(-expo_logit)))

        # rare outcome. Baseline risk is HIGHER in higher strata (confounding by
        # indication); the exposure adds the true causal log-OR; mild secular drift.
        out_logit = -4.8 + 0.45 * stratum + beta1 * exposed - 0.02 * t + 0.25 * U
        outcome = rng.binomial(1, 1.0 / (1.0 + np.exp(-out_logit)))

        expo_all[t * n:(t + 1) * n] = exposed
        out_all[t * n:(t + 1) * n] = outcome

    return pd.DataFrame({
        "pid": np.tile(np.arange(n), t_periods),
        "period": np.repeat(np.arange(t_periods), n),
        "x1": np.tile(x1.round(3), t_periods),
        "x2": np.tile(x2, t_periods),
        "exposed": expo_all,
        "outcome": out_all,
    }, columns=COLUMNS)


if __name__ == "__main__":
    df = generate()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    df.to_csv(OUT, index=False)
    print(f"wrote {OUT}  ({len(df)} rows = {df.pid.nunique()} people × {df.period.nunique()} periods)")
    print("overall outcome rate:", round(df.outcome.mean(), 4))
    print("exposure prevalence by period:",
          [round(v, 3) for v in df.groupby('period').exposed.mean().tolist()])
    # naive (confounded) OR of outcome ~ exposed
    a = ((df.exposed == 1) & (df.outcome == 1)).sum()
    b = ((df.exposed == 1) & (df.outcome == 0)).sum()
    c = ((df.exposed == 0) & (df.outcome == 1)).sum()
    d = ((df.exposed == 0) & (df.outcome == 0)).sum()
    print("naive OR =", round((a * d) / (b * c), 3), " (true OR =", TRUE_OR, ")")

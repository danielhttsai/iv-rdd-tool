"""Built-in DEMO dataset for the Active-Comparator, New-User (ACNU) tabs.

Fully fictional teaching scenario — NOT real data:

    情境：想知道某個<b>新藥 A</b>會不會提高某個<b>結果</b>（這裡借用「心血管事件」）的風險。
          天真的做法是拿「用 A 的人 vs 沒用藥的人」比——但會用 A 的人本來病情就比較重
          （<b>因適應症而生的混淆</b>，confounding by indication），而沒用藥的人通常比較健康
          （<b>healthy-user</b>）。把這兩群直接比，A 會被冤枉成有害。
          ACNU 的解法：只比<b>新使用者</b>——把 A 的<b>新使用者</b>拿來和一個<b>主動對照藥 B</b>
          （治療<b>同一個適應症</b>、病人相似）的<b>新使用者</b>比。兩組都有這個病、都剛開始用藥、
          時間零點明確（第一張處方），就把「因適應症而生的混淆」和 immortal-time／prevalent-user
          偏誤一起大幅削掉。A 和 B 之間若還有殘留的嚴重度差，再用傾向分數校正。

每筆資料：pid、drug（"A" / "B" / "none"）、severity（疾病嚴重度，連續，混淆因子）、age、
          comorbidity、futime（追蹤人時，年）、event（追蹤內是否發生結果）。
          真實（A 相對 B 的）速率比 TRUE_HR（這裡 1.6）。
"""
from __future__ import annotations

import os
import numpy as np
import pandas as pd

SEED = 41
N = 60000
TRUE_HR = 1.6              # true rate ratio of drug A vs the active comparator B
HORIZON = 2.0             # follow-up horizon (years)

# treatment-choice model among the INDICATED (confounding by indication):
#   sicker (higher severity) patients are preferentially put on A rather than B.
G0, G_SEV = 0.0, 1.4      # P(A | treated) = sigmoid(G0 + G_SEV*conf*severity)
# baseline event hazard model: severity (the confounder) drives the event rate.
BASE, B_SEV, B_COM = 0.10, 0.85, 0.30
COLUMNS = ["pid", "drug", "severity", "age", "comorbidity", "futime", "event"]

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "demo_acnu.csv")


def _sig(x):
    return 1.0 / (1.0 + np.exp(-x))


def generate(seed=SEED, n=N, true_hr=TRUE_HR, conf=1.0, horizon=HORIZON):
    """Simulate an indicated cohort. SEVERITY confounds (sicker patients get drug A AND
    have higher event rates). Three groups:
      A    — new users of the study drug (skew toward higher severity when conf>0),
      B    — new users of the active comparator (same indication, slightly lower severity),
      none — untreated people who are systematically HEALTHIER (healthy-user).
    Truth = the A-vs-B rate ratio `true_hr`. The naive 'A vs none' contrast is badly biased
    (indication + healthy-user); crude ACNU 'A vs B' is much less biased (both indicated);
    severity-adjusted ACNU recovers the truth."""
    rng = np.random.default_rng(seed)
    age = rng.integers(45, 85, n).astype(float)
    severity = rng.normal(0.0, 1.0, n)                     # disease severity (confounder)
    comorb = (rng.random(n) < _sig(-0.5 + 0.4 * severity)).astype(int)

    # who is treated at all: the more severe are more likely to be on a drug; the untreated
    # ("none") are therefore healthier on average (healthy-user / confounding by indication).
    p_treated = _sig(0.2 + 1.2 * severity)
    treated = rng.random(n) < p_treated
    # among the treated, choice of A vs the active comparator B depends on severity (conf):
    p_A = _sig(G0 + G_SEV * conf * severity)
    is_A = treated & (rng.random(n) < p_A)
    is_B = treated & ~(rng.random(n) < p_A)
    # rebuild B as treated-and-not-A so the two partition the treated cleanly
    is_B = treated & ~is_A
    drug = np.where(is_A, "A", np.where(is_B, "B", "none"))

    # event rate: baseline hazard rises with severity & comorbidity; drug A multiplies the
    # hazard by true_hr, drug B and none by 1 (B is the reference; none simply untreated).
    mult = np.where(drug == "A", true_hr, 1.0)
    lam = BASE * np.exp(B_SEV * severity + B_COM * comorb) * mult
    lam = np.clip(lam, 1e-4, None)
    evt_time = rng.exponential(1.0 / lam)                   # time to event (years)
    futime = np.minimum(evt_time, horizon)
    event = (evt_time <= horizon).astype(int)

    return pd.DataFrame({
        "pid": np.arange(n),
        "drug": drug,
        "severity": np.round(severity, 3),
        "age": age.astype(int),
        "comorbidity": comorb,
        "futime": np.round(futime, 4),
        "event": event,
    }, columns=COLUMNS)


if __name__ == "__main__":
    df = generate()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    df.to_csv(OUT, index=False)
    def irr(g1, g2):
        s1 = df[df.drug == g1]; s2 = df[df.drug == g2]
        r1 = s1.event.sum() / s1.futime.sum(); r2 = s2.event.sum() / s2.futime.sum()
        return r1 / r2
    print(f"wrote {OUT}  ({len(df)} rows; A={int((df.drug=='A').sum())}, "
          f"B={int((df.drug=='B').sum())}, none={int((df.drug=='none').sum())})")
    print("naive IRR  A vs none =", round(irr('A', 'none'), 3), " (true", TRUE_HR, ")")
    print("ACNU crude IRR A vs B =", round(irr('A', 'B'), 3))
    for g in ("A", "B", "none"):
        print(f"  mean severity[{g}] =", round(df[df.drug == g].severity.mean(), 3))

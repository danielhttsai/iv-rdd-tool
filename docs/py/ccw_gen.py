"""Generate the built-in DEMO dataset for the Clone-Censor-Weight (CCW) tabs.

Fully fictional teaching scenario — NOT real data. We emulate a *target trial* of
treatment TIMING after a diagnosis, in the same vaccine spirit used elsewhere:

    情境：一群人在第 0 月被診斷。之後每個月，還沒接種、也還沒發生事件的人，可能會去接種
          （是否接種、何時接種，與「體弱程度 frailty」有關 —— 體弱的人傾向更早去打，這就是
          confounding by indication）。疫苗有真正的保護效果：打完之後，每月發生「重大健康
          事件」的風險下降。我們想比較兩種**策略**：
              早接種（early）：在寬限期 g 個月內接種
              晚接種／延後（late）：寬限期內先不接種
          天真地「照實際分組比」會中 immortal-time bias（被歸到 early 的人，必須先活著、沒發生
          事件，才有機會早接種 → early 組看起來假性更健康）。Clone-censor-weight 把每個人
          『複製』到兩個策略、在『偏離指派策略』時設限、再用反設限機率加權，去掉這個偏誤。

    個體     i，自診斷起追蹤 T 個月
    共變項   age、frailty（皆可測；無未測混淆）
    接種時間 vacc_month（第幾個月接種；若追蹤期內未接種則為 NaN）
    事件     event（追蹤期內是否發生重大健康事件）、futime（事件或追蹤結束的月份）

真實策略效應（風險差）由「強制策略」的大樣本蒙地卡羅算出，存成 TRUE_RD（早 − 晚，負值＝早接
種較保護）。這是 CCW 應該還原、而天真比較會偏離的目標。
"""
from __future__ import annotations

import os
import numpy as np
import pandas as pd

SEED = 73
N = 6000          # individuals
T = 12            # months of follow-up after diagnosis
GRACE = 3         # grace period (months): early = initiate within [0, GRACE]

# event monthly-hazard logit coefficients
B0 = -2.7         # baseline monthly event log-odds
B_FRAIL = 1.15    # frailty raises event risk
B_AGE = 0.45      # standardized age raises event risk
B_PROT = 1.30     # vaccination LOWERS event log-odds (the true protective effect)

# initiation monthly-hazard logit coefficients (among not-yet-vaccinated, event-free)
A0 = -1.15        # baseline monthly initiation log-odds
A_FRAIL = 1.00    # frail people initiate SOONER → confounding by indication
A_AGE = 0.30

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "demo_ccw.csv")
COLUMNS = ["pid", "age", "frailty", "vacc_month", "event", "futime"]


def _sig(x):
    return 1.0 / (1.0 + np.exp(-x))


def _simulate(rng, age_std, frail, timing_effect=1.0, force=None, init_confound=True):
    """One monthly simulation over N people. Returns vacc_month, event, futime arrays.

    force = None        → observational (people initiate per their own hazard)
    force = "early"     → everyone initiates at month 0
    force = "late"      → nobody initiates during follow-up (the deferral/control arm)
    timing_effect scales the protective effect's dependence on being treated, used by
    the ② slider (0 → vaccination does nothing; 1 → full protective effect).
    init_confound = False → initiation timing is INDEPENDENT of frailty/age (no
    confounding by indication). Used to compute the estimand's ground truth: there
    the clone-censor estimate is unbiased because the weights are ≈ 1.
    """
    n = age_std.size
    vacc = np.full(n, -1, dtype=int)       # -1 = not yet vaccinated
    if force == "early":
        vacc[:] = 0
    evt_month = np.full(n, -1, dtype=int)  # -1 = no event yet
    alive = np.ones(n, dtype=bool)         # event-free & in follow-up
    prot = B_PROT * float(timing_effect)
    a_frail = A_FRAIL if init_confound else 0.0
    a_age = A_AGE if init_confound else 0.0
    # keep the marginal initiation rate similar when confounding is off
    a0 = A0 if init_confound else (A0 + 0.5 * A_FRAIL * 0.4)

    for t in range(T):
        treated_now = (vacc >= 0) & (vacc < t)          # immunity from the month AFTER initiation
        # event hazard this month
        h_evt = _sig(B0 + B_FRAIL * frail + B_AGE * age_std - prot * treated_now)
        draw_e = rng.random(n) < h_evt
        new_evt = alive & draw_e
        evt_month[new_evt] = t
        alive = alive & ~new_evt
        # initiation this month (only observational / not-yet-vaccinated / still alive)
        if force is None:
            elig = alive & (vacc < 0)
            h_init = _sig(a0 + a_frail * frail + a_age * age_std)
            draw_i = rng.random(n) < h_init
            new_i = elig & draw_i
            vacc[new_i] = t
        # force=="late": never initiate (vacc stays -1)
        # force=="early": already set vacc=0

    event = (evt_month >= 0).astype(int)
    futime = np.where(evt_month >= 0, evt_month + 1, T)
    vacc_month = np.where(vacc >= 0, vacc, np.nan)
    return vacc_month, event, futime


def generate(n=N, seed=SEED, timing_effect=1.0, init_confound=True):
    rng = np.random.default_rng(seed)
    age = rng.normal(70, 8, n)
    age_std = (age - 70.0) / 10.0
    frail = rng.binomial(1, 0.4, n).astype(float)
    vacc_month, event, futime = _simulate(rng, age_std, frail, timing_effect=timing_effect,
                                           force=None, init_confound=init_confound)
    return pd.DataFrame({
        "pid": np.arange(n),
        "age": age.round(1),
        "frailty": frail.astype(int),
        "vacc_month": vacc_month,
        "event": event,
        "futime": futime,
    }, columns=COLUMNS)


def true_rd(timing_effect=1.0, n=200000, seed=99):
    """True strategy contrast = risk(early) − risk(late) at the horizon T,
    from large-N forced-strategy Monte Carlo (early = treat at 0, late = never)."""
    rng = np.random.default_rng(seed)
    age_std = (rng.normal(70, 8, n) - 70.0) / 10.0
    frail = rng.binomial(1, 0.4, n).astype(float)
    _, e_early, _ = _simulate(rng, age_std, frail, timing_effect=timing_effect, force="early")
    _, e_late, _ = _simulate(rng, age_std, frail, timing_effect=timing_effect, force="late")
    return float(e_early.mean() - e_late.mean())


# Headline truth of the CCW estimand (early vs late), precomputed offline. This is
# the value the clone-censor-weight estimator targets; see ccw_core.estimand_truth.
# (NOT computed at import — that would slow the Pyodide module load.)
TRUE_RD = -0.224


if __name__ == "__main__":
    df = generate()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    df.to_csv(OUT, index=False)
    print(f"wrote {OUT}  ({len(df)} people × {T} months, grace={GRACE})")
    print("vaccinated within follow-up:", round(df.vacc_month.notna().mean(), 3))
    print("initiated within grace [0,g]:",
          round((df.vacc_month <= GRACE).mean(), 3))
    print("overall event rate:", round(df.event.mean(), 3))
    print("TRUE_RD (early - late) =", round(TRUE_RD, 4))

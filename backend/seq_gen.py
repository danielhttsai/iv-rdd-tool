"""Generate the built-in DEMO dataset for the Sequential (nested) trials tabs.

Fully fictional teaching scenario — NOT real data:

    情境：一個<b>點治療</b>決定（當下治療 vs 不治療）。病人在不同月份<b>陸續符合資格</b>；每個月，
          還沒治療、也還沒發生事件的合格者，可能在「當下」啟動治療（是否啟動與體弱程度有關＝混淆）。
          治療有真正的保護效果。我們在<b>每個資格月開一場巢式 mini-trial</b>（當月啟動 vs 當月不啟動）、
          對齊時間零點，再把多場合併。同一個人可在多個資格月被重複納入（放大有效樣本數）。
          天真地比「曾治療 vs 從未治療」會中 immortal-time bias（曾治療者必須先活著、撐到治療那刻）。

    個體     pid，自診斷起追蹤；共變項 age、frailty（皆可測）
    啟動時間 init_month（第幾個月啟動治療；NaN＝追蹤期內未啟動）
    事件     event（是否發生）、futime（事件或追蹤結束月份）

真實點治療效應（風險差）＝「當下治療 vs 從不治療」到 horizon 的風險差，由強制策略蒙地卡羅算出。
序列（巢式）試驗應該還原它，而天真比較會偏離。
"""
from __future__ import annotations

import os
import numpy as np
import pandas as pd

SEED = 57
N = 6000
T = 12             # months of follow-up
HORIZON = 12       # outcome horizon (event by end of follow-up)
N_TRIALS = 6       # nested trials at eligibility months 0..N_TRIALS-1

B0, B_FRAIL, B_AGE, B_PROT = -2.7, 1.15, 0.45, 1.30      # event hazard
A0, A_FRAIL, A_AGE, A_TIME = -1.6, 1.0, 0.30, 0.05       # initiation hazard

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "data", "demo_seq.csv")
COLUMNS = ["pid", "age", "frailty", "init_month", "event", "futime"]


def _sig(x):
    return 1.0 / (1.0 + np.exp(-x))


def _simulate(rng, age_std, frail, timing_effect=1.0, conf=1.0, force=None):
    """Monthly point-treatment simulation. `conf` scales confounding-by-indication
    in the initiation hazard (0 → initiation independent of covariates → naive
    unbiased; 1 → full confounding). force='treat' (initiate at 0) / 'never'."""
    n = age_std.size
    init = np.full(n, -1, dtype=int)
    if force == "treat":
        init[:] = 0
    evt = np.full(n, -1, dtype=int)
    alive = np.ones(n, dtype=bool)
    prot = B_PROT * float(timing_effect)
    for t in range(T):
        treated_now = (init >= 0) & (init < t)
        h_evt = _sig(B0 + B_FRAIL * frail + B_AGE * age_std - prot * treated_now)
        new_e = alive & (rng.random(n) < h_evt)
        evt[new_e] = t; alive = alive & ~new_e
        if force is None:
            elig = alive & (init < 0)
            h_init = _sig(A0 + conf * (A_FRAIL * frail + A_AGE * age_std) + A_TIME * t)
            init[elig & (rng.random(n) < h_init)] = t
        # force=='never': never initiate; force=='treat': init=0 already
    event = (evt >= 0).astype(int)
    futime = np.where(evt >= 0, evt + 1, T)
    init_month = np.where(init >= 0, init, np.nan)
    return init_month, event, futime


def generate(n=N, seed=SEED, timing_effect=1.0, conf=1.0):
    rng = np.random.default_rng(seed)
    age = rng.normal(70, 8, n); age_std = (age - 70.0) / 10.0
    frail = rng.binomial(1, 0.4, n).astype(float)
    init_month, event, futime = _simulate(rng, age_std, frail, timing_effect=timing_effect, conf=conf)
    return pd.DataFrame({
        "pid": np.arange(n), "age": age.round(1), "frailty": frail.astype(int),
        "init_month": init_month, "event": event, "futime": futime,
    }, columns=COLUMNS)


def true_rd(timing_effect=1.0, n=200000, seed=99):
    """True point-treatment risk difference = risk(treat at 0) − risk(never) at the
    horizon, from forced-strategy Monte Carlo."""
    rng = np.random.default_rng(seed)
    age_std = (rng.normal(70, 8, n) - 70.0) / 10.0
    frail = rng.binomial(1, 0.4, n).astype(float)
    _, e_tr, _ = _simulate(rng, age_std, frail, timing_effect=timing_effect, force="treat")
    _, e_nv, _ = _simulate(rng, age_std, frail, timing_effect=timing_effect, force="never")
    return float(e_tr.mean() - e_nv.mean())


TRUE_RD = -0.224   # headline truth (timing_effect=1), precomputed offline


if __name__ == "__main__":
    df = generate()
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    df.to_csv(OUT, index=False)
    print(f"wrote {OUT}  ({len(df)} people × {T} months)")
    print("ever treated:", round(df.init_month.notna().mean(), 3))
    print("event rate:", round(df.event.mean(), 3))
    print("TRUE_RD (treat-at-0 − never) =", round(true_rd(), 4))

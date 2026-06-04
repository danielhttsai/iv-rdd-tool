"""FastAPI backend for the IV web tool.

Serves the static frontend and a small JSON API that wraps iv_core + assumptions.
Run:  uvicorn app:app --reload --port 8000   (from this backend/ directory)
"""
from __future__ import annotations

import io
import os
import uuid

import numpy as np
import pandas as pd
from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import assumptions
import iv_core
import ml_iv
import rdd_core
import rdd_survival
import rdd_assumptions
import rdd_ml
import did_core
import did_gen
import did_assumptions
import did_ml
import tit_core
import tit_gen
import tit_assumptions
import its_core
import its_gen
import its_assumptions
import its_ml
import perr_core
import perr_gen
import perr_assumptions
import ccw_core
import ccw_gen
import ccw_assumptions

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data", "demo_vaccine.csv")
DATA_RDD = os.path.join(HERE, "data", "demo_rdd.csv")
DATA_DID = os.path.join(HERE, "data", "demo_did.csv")
DATA_TIT = os.path.join(HERE, "data", "demo_tit.csv")
DATA_ITS = os.path.join(HERE, "data", "demo_its.csv")
DATA_PERR = os.path.join(HERE, "data", "demo_perr.csv")
FRONTEND = os.path.abspath(os.path.join(HERE, "..", "frontend"))

PERR_DEFAULTS = {"group": "group", "events_prior": "events_prior", "pt_prior": "pt_prior",
                 "events_post": "events_post", "pt_post": "pt_post"}
CCW_DEFAULTS = {"vacc_time": "vacc_month", "event": "event", "futime": "futime",
                "covariates": ["age", "frailty"], "grace": 3, "horizon": 12}

TIT_DEFAULTS = {"covariates": ["x1", "x2"], "K": 5}
ITS_DEFAULTS = {"outcome": "outcome", "time": "time", "post": "post", "t_since": "t_since"}

DID_DEFAULTS = {
    "unit": "unit",
    "period": "period",
    "group": "treated",
    "outcome": "health_score",
    "t0": 3,
    "covariates": ["urban", "baseline_burden"],
}

RDD_DEFAULTS = {
    "running": "age",
    "outcome": "health_score_change",
    "treatment": "vaccinated",
    "cutoff": 65.0,
    "time": "event_time",
    "event": "event",
    "covariates": ["female", "bmi", "chronic_conditions", "income_band"],
}

EXAMPLE_DEFAULTS = {
    "outcome": "health_score_change",
    "treatment": "vaccinated",
    "instrument": "vaccine_reminder",
    "covariates": ["age", "female", "bmi", "chronic_conditions", "income_band"],
}

DISCLAIMER = "⚠ 純屬虛構的合成示範資料,非真實病人/個資,僅供教學展示。"

app = FastAPI(title="IV 工具線上版")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

# In-memory store of uploaded datasets: token -> DataFrame (single-user teaching tool).
_UPLOADS: dict[str, pd.DataFrame] = {}


def _load(source: str) -> pd.DataFrame:
    if source == "example":
        return pd.read_csv(DATA)
    df = _UPLOADS.get(source)
    if df is None:
        raise HTTPException(404, "找不到資料，請重新上傳。")
    return df


def _clean(obj):
    """Make numpy/NaN values JSON-safe."""
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items() if not k.startswith("_")}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, (np.floating, float)):
        f = float(obj)
        return None if (np.isnan(f) or np.isinf(f)) else f
    if isinstance(obj, (np.integer,)):
        return int(obj)
    return obj


class AnalyzeRequest(BaseModel):
    source: str = "example"
    outcome: str
    treatment: str
    instrument: str
    covariates: list[str] = []
    lang: str = "zh"


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------
@app.get("/api/example")
def example_preview():
    df = pd.read_csv(DATA)
    return _clean({
        "columns": list(df.columns),
        "defaults": EXAMPLE_DEFAULTS,
        "n": len(df),
        "synthetic": True,
        "disclaimer": DISCLAIMER,
        "preview": df.head(8).to_dict(orient="records"),
        "story": {
            "instrument": "vaccine_reminder（住在被隨機抽中、收到免費接種提醒的社區）",
            "treatment": "vaccinated（是否接種疫苗）",
            "outcome": "health_score_change（一年後健康分數的變化）",
        },
    })


@app.post("/api/upload")
async def upload(file: UploadFile = File(...)):
    raw = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(raw))
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(400, f"無法讀取 CSV：{exc}")
    numeric = df.select_dtypes(include="number").columns.tolist()
    if not numeric:
        raise HTTPException(400, "資料中找不到數值欄位。")
    token = uuid.uuid4().hex
    _UPLOADS[token] = df
    return _clean({
        "token": token,
        "columns": df.columns.tolist(),
        "numeric_columns": numeric,
        "n": len(df),
        "preview": df.head(8).to_dict(orient="records"),
    })


def _validate(df, req: AnalyzeRequest):
    needed = [req.outcome, req.treatment, req.instrument, *req.covariates]
    missing = [c for c in needed if c not in df.columns]
    if missing:
        raise HTTPException(400, f"資料缺少欄位：{', '.join(missing)}")


@app.post("/api/analyze")
def analyze(req: AnalyzeRequest):
    df = _load(req.source)
    _validate(df, req)
    out = iv_core.full_analysis(
        df, req.outcome, req.treatment, req.instrument, req.covariates, lang=req.lang
    )
    return _clean(out)


@app.post("/api/assumptions")
def check_assumptions(req: AnalyzeRequest):
    df = _load(req.source)
    _validate(df, req)
    out = assumptions.check_all(
        df, req.outcome, req.treatment, req.instrument, req.covariates, lang=req.lang
    )
    return _clean(out)


@app.get("/api/interactive")
def interactive(complier_share: float = 0.063, strength: float = 1.0, seed: int = 7):
    """Simulate a fresh dataset for the teaching slider and return the Wald estimate.

    complier_share : first-stage coefficient (fraction of compliers)
    strength       : 0.2..2.0 scales sample size / signal -> tighter or wider CI
    """
    complier_share = float(np.clip(complier_share, 0.01, 0.5))
    strength = float(np.clip(strength, 0.2, 2.0))
    rng = np.random.default_rng(seed)
    n = int(2000 * strength)
    true_late = 1.80

    Z = rng.binomial(1, 0.5, n)
    U = rng.standard_normal(n)
    p = np.clip(0.30 + complier_share * Z + 0.12 * U, 0.02, 0.98)
    A = rng.binomial(1, p)
    Y = true_late * A + 1.50 * U + rng.normal(0, 3.0, n)
    df = pd.DataFrame({"Y": Y, "A": A, "Z": Z})

    fs = iv_core.first_stage(df, "A", "Z")
    iv = iv_core.iv_2sls(df, "Y", "A", "Z")
    return _clean({
        "complier_share": complier_share,
        "strength": strength,
        "n": n,
        "first_coef": fs["coef"],
        "f_stat": fs["f_stat"],
        "estimate": iv["estimate"],
        "ci": iv["ci"],
        "true_late": true_late,
    })


# ---------------------------------------------------------------------------
# Machine-learning + IV demos (tab 5)
# ---------------------------------------------------------------------------
@app.get("/api/ml_synthesis")
def ml_synthesis(k_candidates: int = 12, per_strength: float = 0.03, n: int = 6000, seed: int = 7):
    """藥方一：把多個弱工具合成一個強工具（含交叉擬合）。"""
    return _clean(ml_iv.synthesis_demo(
        n=n, k_candidates=k_candidates, per_strength=per_strength, seed=seed
    ))


@app.get("/api/ml_nonlinear")
def ml_nonlinear(n: int = 8000, seed: int = 11):
    """藥方二：直線第一階段 vs 可彎的第一階段。"""
    return _clean(ml_iv.nonlinear_demo(n=n, seed=seed))


@app.get("/api/ml_forbidden")
def ml_forbidden(seed: int = 7):
    """藥方三：同一個樹模型，偷看版（禁止迴歸）vs 交叉擬合版。"""
    return _clean(ml_iv.forbidden_demo(seed=seed))


@app.get("/api/ml_compare")
def ml_compare(seed: int = 7, lang: str = "zh"):
    """把各種做法放在一起比較。"""
    return _clean(ml_iv.compare(seed=seed, lang=lang))


# ---------------------------------------------------------------------------
# Regression Discontinuity (tabs 6 & 7) — same vaccine scenario, age-65 cutoff
# ---------------------------------------------------------------------------
class RddRequest(BaseModel):
    source: str = "example_rdd"
    running: str = "age"
    outcome: str = "health_score_change"
    treatment: str = "vaccinated"
    cutoff: float = 65.0
    bandwidth: float | None = None
    covariates: list[str] = ["female", "bmi", "chronic_conditions", "income_band"]
    time: str = "event_time"
    event: str = "event"
    lang: str = "zh"


def _load_rdd(source: str) -> pd.DataFrame:
    if source in ("example_rdd", "example"):
        return pd.read_csv(DATA_RDD)
    df = _UPLOADS.get(source)
    if df is None:
        raise HTTPException(404, "找不到資料，請重新上傳。")
    return df


@app.get("/api/rdd_example")
def rdd_example():
    df = pd.read_csv(DATA_RDD)
    return _clean({
        "columns": list(df.columns),
        "defaults": RDD_DEFAULTS,
        "n": len(df),
        "synthetic": True,
        "disclaimer": DISCLAIMER,
        "preview": df.head(8).to_dict(orient="records"),
        "story": {
            "running": "age（年齡，跑分變數）",
            "cutoff": "65（滿 65 歲才有免費接種計畫資格）",
            "treatment": "vaccinated（實際是否接種）",
            "outcome": "health_score_change（一年後健康分數變化）",
        },
    })


@app.post("/api/rdd_analyze")
def rdd_analyze(req: RddRequest):
    df = _load_rdd(req.source)
    out = rdd_core.full_rdd(
        df, req.running, req.outcome, req.treatment, req.cutoff,
        h=req.bandwidth, lang=req.lang,
    )
    return _clean(out)


@app.post("/api/rdd_assumptions")
def rdd_assumptions_check(req: RddRequest):
    df = _load_rdd(req.source)
    h = req.bandwidth or rdd_core.default_bandwidth(
        np.asarray(df[req.running], dtype=float), req.cutoff
    )
    out = rdd_assumptions.run_dashboard(
        df, req.running, req.outcome, req.treatment, req.cutoff, h,
        req.covariates, fuzzy=True, lang=req.lang,
    )
    return _clean(out)


@app.post("/api/rdd_survival")
def rdd_survival_check(req: RddRequest):
    df = _load_rdd(req.source)
    naive = rdd_survival.naive_survival_rd(
        df, req.running, req.time, req.cutoff, h=req.bandwidth, lang=req.lang
    )
    sharp = rdd_survival.survival_rd(
        df, req.running, req.time, req.event, req.cutoff,
        h=req.bandwidth, lang=req.lang,
    )
    fuzzy = rdd_survival.survival_rd(
        df, req.running, req.time, req.event, req.cutoff,
        h=req.bandwidth, d_name=req.treatment, fuzzy=True, lang=req.lang,
    )
    return _clean({"naive": naive, "sharp": sharp, "fuzzy": fuzzy})


@app.get("/api/rdd_interactive")
def rdd_interactive(bandwidth: float = 6.0, lang: str = "zh"):
    """Teaching slider: re-estimate sharp & fuzzy RD at the chosen bandwidth."""
    df = pd.read_csv(DATA_RDD)
    bandwidth = float(np.clip(bandwidth, 2.0, 14.0))
    out = rdd_core.full_rdd(
        df, "age", "health_score_change", "vaccinated", 65.0, h=bandwidth, lang=lang
    )
    return _clean({
        "bandwidth": bandwidth,
        "sharp": out["sharp"]["estimate"], "sharp_ci": out["sharp"]["ci"],
        "fuzzy": out["fuzzy"]["estimate"], "fuzzy_ci": out["fuzzy"]["ci"],
        "takeup_jump": out["takeup"]["estimate"],
        "n_left": out["sharp"]["n_left"], "n_right": out["sharp"]["n_right"],
        "true_late": 1.80,
    })


# ---------------------------------------------------------------------------
# Machine-learning + RDD demos (RDD tab ⑤) — DML + flexible-ML survival
# ---------------------------------------------------------------------------
@app.get("/api/rdd_ml_bandwidth")
def rdd_ml_bandwidth(window: float = 8.0, seed: int = 7):
    """藥方一：視窗內直接比較 vs 交叉擬合的雙重穩健 DML（不挑視窗）。"""
    return _clean(rdd_ml.dml_bandwidth_demo(window=window, seed=seed))


@app.get("/api/rdd_ml_survival")
def rdd_ml_survival(seed: int = 11, lang: str = "zh"):
    """藥方二：帶設限的存活結果——未處理 vs IPCW vs 彈性 ML 雙重穩健。"""
    return _clean(rdd_ml.survival_robust_demo(seed=seed, lang=lang))


# ---------------------------------------------------------------------------
# Difference-in-differences (DiD method) — policy switched on for some units at t0
# ---------------------------------------------------------------------------
class DidRequest(BaseModel):
    source: str = "example_did"
    unit: str = "unit"
    period: str = "period"
    group: str = "treated"
    outcome: str = "health_score"
    t0: float = 3.0
    covariates: list[str] = ["urban", "baseline_burden"]
    lang: str = "zh"


def _load_did(source: str) -> pd.DataFrame:
    if source in ("example_did", "example"):
        return pd.read_csv(DATA_DID)
    df = _UPLOADS.get(source)
    if df is None:
        raise HTTPException(404, "找不到資料，請重新上傳。")
    return df


@app.get("/api/did_example")
def did_example():
    df = pd.read_csv(DATA_DID)
    return _clean({
        "columns": list(df.columns),
        "defaults": DID_DEFAULTS,
        "n": len(df),
        "synthetic": True,
        "disclaimer": DISCLAIMER,
        "preview": df.head(8).to_dict(orient="records"),
        "story": {
            "unit": "unit（社區／診區，固定追蹤的面板單位）",
            "period": "period（0–5 期，第 3 期起為政策後）",
            "group": "treated（1＝介入組社區，0＝對照組）",
            "outcome": "health_score（該社區當期平均健康分數）",
        },
    })


@app.post("/api/did_analyze")
def did_analyze(req: DidRequest):
    df = _load_did(req.source)
    out = did_core.full_did(
        df, req.unit, req.period, req.group, req.outcome,
        t0=req.t0, covariates=req.covariates, lang=req.lang,
    )
    return _clean(out)


@app.post("/api/did_assumptions")
def did_assumptions_check(req: DidRequest):
    df = _load_did(req.source)
    out = did_assumptions.run_dashboard(
        df, req.unit, req.period, req.group, req.outcome,
        t0=req.t0, covariates=req.covariates, lang=req.lang,
    )
    return _clean(out)


@app.get("/api/did_interactive")
def did_interactive(violation: float = 0.0, lang: str = "zh"):
    """Teaching slider: re-generate the panel with a pre-trend `violation` and show
    how the DiD estimate drifts and the event-study pre-period dots lift off zero."""
    violation = float(np.clip(violation, 0.0, 1.5))
    df = did_gen.generate(violation=violation)
    out = did_core.full_did(df, "unit", "period", "treated", "health_score",
                            t0=did_gen.T0, lang=lang)
    return _clean({
        "violation": violation,
        "true_att": did_gen.TRUE_ATT,
        "estimate": out["did"]["estimate"], "ci": out["did"]["ci"],
        "naive": out["naive_difference"],
        "event_study": out["event_study"],
        "trend": out["trend"],
        "t0": did_gen.T0,
    })


@app.get("/api/did_variants")
def did_variants(seed: int = 7, lang: str = "zh"):
    """DiD ③ advanced VARIANTS (not AI): staggered, universal, synthetic control."""
    return _clean(did_ml.variant_demos(seed=seed, lang=lang))


@app.get("/api/did_dml")
def did_dml(seed: int = 7, lang: str = "zh"):
    """DiD ⑤: a GENUINE machine-learning estimator — double/debiased ML DiD (sklearn)."""
    return _clean(did_ml.dml_demo(seed=seed, lang=lang))


# ---------------------------------------------------------------------------
# Trend-in-trend (TiT method) — a drug whose uptake trends over calendar time
# ---------------------------------------------------------------------------
class TitRequest(BaseModel):
    source: str = "example_tit"
    covariates: list[str] = ["x1", "x2"]
    K: int = 5
    lang: str = "zh"


def _load_tit(source: str) -> pd.DataFrame:
    if source in ("example_tit", "example"):
        return pd.read_csv(DATA_TIT)
    df = _UPLOADS.get(source)
    if df is None:
        raise HTTPException(404, "找不到資料，請重新上傳。")
    return df


@app.get("/api/tit_example")
def tit_example():
    df = pd.read_csv(DATA_TIT)
    return _clean({
        "columns": list(df.columns),
        "defaults": TIT_DEFAULTS,
        "n_rows": len(df),
        "n_people": int(df["pid"].nunique()),
        "synthetic": True,
        "disclaimer": DISCLAIMER,
        "preview": df.head(8).to_dict(orient="records"),
        "story": {
            "pid": "pid（個體 id，跨期追蹤）",
            "period": "period（0–9 季，新藥逐漸普及）",
            "exposed": "exposed（當期是否用藥，二元）",
            "outcome": "outcome（罕見不良事件，二元）",
            "covariates": "x1, x2（基線特徵，用來算 CPE 分層）",
        },
    })


@app.post("/api/tit_analyze")
def tit_analyze(req: TitRequest):
    df = _load_tit(req.source)
    return _clean(tit_core.full_tit(df, covariates=tuple(req.covariates), K=req.K, lang=req.lang))


@app.post("/api/tit_assumptions")
def tit_assumptions_check(req: TitRequest):
    df = _load_tit(req.source)
    return _clean(tit_assumptions.run_dashboard(df, covariates=tuple(req.covariates), K=req.K, lang=req.lang))


@app.get("/api/its_example")
def its_example():
    df = pd.read_csv(DATA_ITS)
    return _clean({
        "columns": list(df.columns), "defaults": ITS_DEFAULTS, "n": len(df),
        "synthetic": True, "disclaimer": DISCLAIMER,
        "preview": df.head(8).to_dict(orient="records"),
        "story": {
            "time": "time（期序，等間隔的月）",
            "post": "post（1＝介入後）",
            "t_since": "t_since（介入後經過幾期）",
            "outcome": "outcome（每月健康負擔指數）",
        },
    })


class ItsRequest(BaseModel):
    source: str = "example_its"
    outcome: str = "outcome"
    time: str = "time"
    post: str = "post"
    t_since: str = "t_since"
    lang: str = "zh"


def _load_its(source: str) -> pd.DataFrame:
    if source in ("example_its", "example"):
        return pd.read_csv(DATA_ITS)
    df = _UPLOADS.get(source)
    if df is None:
        raise HTTPException(404, "找不到資料，請重新上傳。")
    return df


@app.post("/api/its_analyze")
def its_analyze(req: ItsRequest):
    df = _load_its(req.source)
    return _clean(its_core.full_its(df, req.outcome, req.time, req.post, req.t_since, lang=req.lang))


@app.post("/api/its_assumptions")
def its_assumptions_check(req: ItsRequest):
    df = _load_its(req.source)
    return _clean(its_assumptions.run_dashboard(df, req.outcome, req.time, req.post, req.t_since, lang=req.lang))


@app.get("/api/its_interactive")
def its_interactive(level: float = -12.0, lang: str = "zh"):
    """Teaching slider: re-generate with a chosen intervention LEVEL change and show
    the segmented fit, the extrapolated counterfactual, and the estimated effects."""
    level = float(np.clip(level, -30.0, 30.0))
    df = its_gen.generate(level=level)
    out = its_core.full_its(df, lang=lang)
    return _clean({"level_set": level, "level": out["level"], "slope": out["slope"],
                   "plot": out["plot"], "effect_end": out["effect_end"]})


@app.get("/api/its_variants")
def its_variants(seed: int = 7, lang: str = "zh"):
    """ITS ③ advanced VARIANTS (not AI): HAC SE, controlled/triple-diff, BSTS."""
    return _clean(its_ml.variant_demos(seed=seed, lang=lang))


@app.get("/api/its_mlcf")
def its_mlcf(seed: int = 7, lang: str = "zh"):
    """ITS ⑤: a GENUINE machine-learning two-stage counterfactual (sklearn)."""
    return _clean(its_ml.mlcf_demo(seed=seed, lang=lang))


# ---------------------------------------------------------------------------
# Prior Event Rate Ratio (PERR method)
# ---------------------------------------------------------------------------
class PerrRequest(BaseModel):
    source: str = "example_perr"
    group: str = "group"
    events_prior: str = "events_prior"
    pt_prior: str = "pt_prior"
    events_post: str = "events_post"
    pt_post: str = "pt_post"
    lang: str = "zh"


def _load_perr(source: str) -> pd.DataFrame:
    if source in ("example_perr", "example"):
        return pd.read_csv(DATA_PERR)
    df = _UPLOADS.get(source)
    if df is None:
        raise HTTPException(404, "找不到資料，請重新上傳。")
    return df


@app.get("/api/perr_example")
def perr_example():
    df = pd.read_csv(DATA_PERR)
    return _clean({
        "columns": list(df.columns), "defaults": PERR_DEFAULTS, "n": len(df),
        "synthetic": True, "disclaimer": DISCLAIMER,
        "preview": df.head(8).to_dict(orient="records"),
        "story": {
            "group": "group（1＝之後用藥的處置組，0＝對照組）",
            "events_prior": "events_prior（事前期事件數）／pt_prior（人時）",
            "events_post": "events_post（事後期事件數）／pt_post（人時）",
        },
    })


@app.post("/api/perr_analyze")
def perr_analyze(req: PerrRequest):
    df = _load_perr(req.source)
    return _clean(perr_core.full_perr(df, req.group, req.events_prior, req.pt_prior,
                                      req.events_post, req.pt_post, lang=req.lang))


@app.post("/api/perr_assumptions")
def perr_assumptions_check(req: PerrRequest):
    df = _load_perr(req.source)
    return _clean(perr_assumptions.run_dashboard(df, req.group, req.events_prior, req.pt_prior,
                                                 req.events_post, req.pt_post, lang=req.lang))


@app.get("/api/perr_interactive")
def perr_interactive(drift: float = 0.0, lang: str = "zh"):
    """Teaching slider: re-generate with `drift` = how much the confounder effect
    changes from prior to post. 0 = time-invariant (PERR recovers truth); larger =
    PERR becomes biased (the key assumption P1 fails)."""
    drift = float(np.clip(drift, 0.0, 1.0))
    df = perr_gen.generate(drift=drift)
    out = perr_core.full_perr(df, lang=lang)
    return _clean({"drift": drift, "true_rr": perr_gen.TRUE_RR,
                   "perr": out["perr"], "ci": out["ci"], "naive_rr": out["naive_rr"],
                   "rr_prior": out["rr_prior"], "rates": out["rates"]})


@app.get("/api/perr_scale")
def perr_scale(seed: int = 7, lang: str = "zh"):
    """PERR ⑤: documented refinement — PERR (multiplicative) vs PERD (additive) scale sensitivity."""
    return _clean(perr_core.scale_demo(seed=seed, lang=lang))


# ---------------------------------------------------------------------------
# Clone-Censor-Weight endpoints (CCW method)
# ---------------------------------------------------------------------------
class CcwRequest(BaseModel):
    source: str = "example_ccw"
    vacc_time: str = "vacc_month"
    event: str = "event"
    futime: str = "futime"
    covariates: list[str] = ["age", "frailty"]
    grace: int = 3
    horizon: int = 12
    n_boot: int = 0
    lang: str = "zh"


def _load_ccw(source: str) -> pd.DataFrame:
    if source in ("example_ccw", "example"):
        return ccw_gen.generate()
    df = _UPLOADS.get(source)
    if df is None:
        raise HTTPException(404, "找不到資料，請重新上傳。")
    return df


@app.get("/api/ccw_example")
def ccw_example():
    df = ccw_gen.generate()
    return _clean({
        "columns": list(df.columns), "defaults": CCW_DEFAULTS, "n": len(df),
        "synthetic": True, "disclaimer": DISCLAIMER,
        "preview": df.head(8).to_dict(orient="records"),
        "story": {
            "vacc_month": "vacc_month（診斷後第幾個月接種；空白＝追蹤期內未接種）",
            "event": "event（追蹤期內是否發生重大健康事件）／futime（事件或追蹤結束月份）",
            "age": "age、frailty（共變項；體弱者傾向更早接種＝適應症混淆）",
        },
    })


@app.post("/api/ccw_analyze")
def ccw_analyze(req: CcwRequest):
    df = _load_ccw(req.source)
    return _clean(ccw_core.full_ccw(df, req.vacc_time, req.event, req.futime,
                                    tuple(req.covariates), req.grace, req.horizon,
                                    n_boot=req.n_boot, lang=req.lang))


@app.post("/api/ccw_assumptions")
def ccw_assumptions_check(req: CcwRequest):
    df = _load_ccw(req.source)
    return _clean(ccw_assumptions.run_dashboard(df, req.vacc_time, req.event, req.futime,
                                                tuple(req.covariates), req.grace, req.horizon,
                                                lang=req.lang))


@app.get("/api/ccw_interactive")
def ccw_interactive(timing_effect: float = 1.0, lang: str = "zh"):
    """Teaching slider: vary the protective effect of vaccination. CCW tracks the
    (changing) truth; the naive immortal-time contrast stays biased."""
    te = float(np.clip(timing_effect, 0.0, 1.0))
    df = ccw_gen.generate(n=3200, timing_effect=te)
    out = ccw_core.full_ccw(df, true_rd=ccw_core.estimand_truth(te), lang=lang)
    return _clean({"timing_effect": te, "true_rd": out["true_rd"], "ccw": out["ccw"],
                   "naive": out["naive"], "curve": out["curve"],
                   "risk_early_ccw": out["risk_early_ccw"], "risk_late_ccw": out["risk_late_ccw"]})


@app.get("/api/ccw_grace")
def ccw_grace(seed: int = 0, lang: str = "zh"):
    """CCW ⑤: grace-period sensitivity — how the estimand/estimate move with g."""
    return _clean(ccw_core.grace_demo(seed=seed, lang=lang))


@app.get("/api/tit_interactive")
def tit_interactive(trend: float = 1.0, lang: str = "zh"):
    """Teaching slider: re-generate with a weaker/stronger exposure time-trend and
    watch the trend-in-trend estimate and its confidence interval respond."""
    trend = float(np.clip(trend, 0.2, 1.5))
    df = tit_gen.generate(n=2500, trend=trend)   # smaller sample → snappy slider
    out = tit_core.full_tit(df, lang=lang)
    return _clean({
        "trend": trend,
        "true_or": tit_gen.TRUE_OR,
        "or": out["or"], "ci": out["ci"], "naive_or": out["naive_or"],
        "exposure_overall": out["exposure_overall"], "exposure_slope": out["exposure_slope"],
        "exposure_curve": out["exposure_curve"], "outcome_curve": out["outcome_curve"],
        "n_periods": out["n_periods"],
    })


# ---------------------------------------------------------------------------
# Static frontend (mounted last so /api/* wins)
# ---------------------------------------------------------------------------
@app.get("/")
def index():
    return FileResponse(os.path.join(FRONTEND, "index.html"))


app.mount("/", StaticFiles(directory=FRONTEND), name="static")

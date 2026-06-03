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

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data", "demo_vaccine.csv")
DATA_RDD = os.path.join(HERE, "data", "demo_rdd.csv")
DATA_DID = os.path.join(HERE, "data", "demo_did.csv")
DATA_TIT = os.path.join(HERE, "data", "demo_tit.csv")
FRONTEND = os.path.abspath(os.path.join(HERE, "..", "frontend"))

TIT_DEFAULTS = {"covariates": ["x1", "x2"], "K": 5}

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


@app.get("/api/did_ml")
def did_ml_demos(seed: int = 7, lang: str = "zh"):
    """DiD ⑤: four advanced remedies (DR/DML, staggered, universal, synthetic control)."""
    return _clean(did_ml.boost_demos(seed=seed, lang=lang))


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

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

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data", "demo_vaccine.csv")
FRONTEND = os.path.abspath(os.path.join(HERE, "..", "frontend"))

EXAMPLE_DEFAULTS = {
    "outcome": "health_score_change",
    "treatment": "vaccinated",
    "instrument": "vaccine_voucher",
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
            "instrument": "vaccine_voucher（住在被隨機抽中、收到免費疫苗券的地區）",
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
        df, req.outcome, req.treatment, req.instrument, req.covariates
    )
    return _clean(out)


@app.post("/api/assumptions")
def check_assumptions(req: AnalyzeRequest):
    df = _load(req.source)
    _validate(df, req)
    out = assumptions.check_all(
        df, req.outcome, req.treatment, req.instrument, req.covariates
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
def ml_compare(seed: int = 7):
    """把各種做法放在一起比較。"""
    return _clean(ml_iv.compare(seed=seed))


# ---------------------------------------------------------------------------
# Static frontend (mounted last so /api/* wins)
# ---------------------------------------------------------------------------
@app.get("/")
def index():
    return FileResponse(os.path.join(FRONTEND, "index.html"))


app.mount("/", StaticFiles(directory=FRONTEND), name="static")

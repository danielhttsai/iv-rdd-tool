"""瀏覽器端 API 橋接 —— 在 Pyodide 裡重現 app.py 的端點,完全不需要伺服器。

繁重的計算照舊由 backend 的 iv_core / assumptions / ml_iv / gen_data 負責,
這裡只是把 FastAPI 的路由邏輯改寫成一個可被 JavaScript 呼叫的 `route()` 函式。
回傳值是 JSON 字串,格式為 {"status": int, "body": ...},由前端的橋接包成 Response。
"""
from __future__ import annotations

import io
import json
import uuid

import numpy as np
import pandas as pd

import assumptions
import iv_core
import ml_iv
import gen_data
import rdd_core
import rdd_survival
import rdd_assumptions
import rdd_gen
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

EXAMPLE_DEFAULTS = {
    "outcome": "health_score_change",
    "treatment": "vaccinated",
    "instrument": "vaccine_reminder",
    "covariates": ["age", "female", "bmi", "chronic_conditions", "income_band"],
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

DID_DEFAULTS = {
    "unit": "unit",
    "period": "period",
    "group": "treated",
    "outcome": "health_score",
    "t0": 3,
    "covariates": ["urban", "baseline_burden"],
}

TIT_DEFAULTS = {"covariates": ["x1", "x2"], "K": 5}
ITS_DEFAULTS = {"outcome": "outcome", "time": "time", "post": "post", "t_since": "t_since"}
PERR_DEFAULTS = {"group": "group", "events_prior": "events_prior", "pt_prior": "pt_prior",
                 "events_post": "events_post", "pt_post": "pt_post"}

DISCLAIMER = "⚠ 純屬虛構的合成示範資料,非真實病人/個資,僅供教學展示。"

_UPLOADS: dict[str, pd.DataFrame] = {}
_DEMO: pd.DataFrame | None = None
_DEMO_RDD: pd.DataFrame | None = None
_DEMO_DID: pd.DataFrame | None = None
_DEMO_TIT: pd.DataFrame | None = None
_DEMO_ITS: pd.DataFrame | None = None
_DEMO_PERR: pd.DataFrame | None = None


def _demo() -> pd.DataFrame:
    global _DEMO
    if _DEMO is None:
        _DEMO = gen_data.generate()
    return _DEMO


def _demo_rdd() -> pd.DataFrame:
    global _DEMO_RDD
    if _DEMO_RDD is None:
        _DEMO_RDD = rdd_gen.generate()
    return _DEMO_RDD


def _demo_did() -> pd.DataFrame:
    global _DEMO_DID
    if _DEMO_DID is None:
        _DEMO_DID = did_gen.generate()
    return _DEMO_DID


def _demo_tit() -> pd.DataFrame:
    global _DEMO_TIT
    if _DEMO_TIT is None:
        _DEMO_TIT = tit_gen.generate()
    return _DEMO_TIT


def _demo_its() -> pd.DataFrame:
    global _DEMO_ITS
    if _DEMO_ITS is None:
        _DEMO_ITS = its_gen.generate()
    return _DEMO_ITS


def _demo_perr() -> pd.DataFrame:
    global _DEMO_PERR
    if _DEMO_PERR is None:
        _DEMO_PERR = perr_gen.generate()
    return _DEMO_PERR


def _clean(obj):
    """Make numpy / NaN values JSON-safe (mirrors app.py._clean)."""
    if isinstance(obj, dict):
        return {k: _clean(v) for k, v in obj.items() if not str(k).startswith("_")}
    if isinstance(obj, (list, tuple)):
        return [_clean(v) for v in obj]
    if isinstance(obj, np.ndarray):
        return [_clean(v) for v in obj.tolist()]
    if isinstance(obj, (np.floating, float)):
        f = float(obj)
        return None if (np.isnan(f) or np.isinf(f)) else f
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    return obj


def _load(source: str) -> pd.DataFrame:
    if source == "example":
        return _demo()
    df = _UPLOADS.get(source)
    if df is None:
        raise ValueError("找不到資料，請重新上傳。")
    return df


def _validate(df: pd.DataFrame, req: dict) -> None:
    needed = [req["outcome"], req["treatment"], req["instrument"], *req.get("covariates", [])]
    missing = [c for c in needed if c not in df.columns]
    if missing:
        raise ValueError("資料缺少欄位：" + ", ".join(missing))


# ---------------------------------------------------------------------------
# Endpoint implementations
# ---------------------------------------------------------------------------
def _example() -> dict:
    df = _demo()
    return {
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
    }


def _upload(text: str) -> dict:
    try:
        df = pd.read_csv(io.StringIO(text))
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"無法讀取 CSV：{exc}")
    numeric = df.select_dtypes(include="number").columns.tolist()
    if not numeric:
        raise ValueError("資料中找不到數值欄位。")
    token = uuid.uuid4().hex
    _UPLOADS[token] = df
    return {
        "token": token,
        "columns": df.columns.tolist(),
        "numeric_columns": numeric,
        "n": len(df),
        "preview": df.head(8).to_dict(orient="records"),
    }


def _analyze(req: dict) -> dict:
    df = _load(req.get("source", "example"))
    _validate(df, req)
    return iv_core.full_analysis(
        df, req["outcome"], req["treatment"], req["instrument"],
        req.get("covariates", []), lang=req.get("lang", "zh"),
    )


def _assumptions(req: dict) -> dict:
    df = _load(req.get("source", "example"))
    _validate(df, req)
    return assumptions.check_all(
        df, req["outcome"], req["treatment"], req["instrument"],
        req.get("covariates", []), lang=req.get("lang", "zh"),
    )


def _interactive(q: dict) -> dict:
    complier_share = float(np.clip(float(q.get("complier_share", 0.063)), 0.01, 0.5))
    strength = float(np.clip(float(q.get("strength", 1.0)), 0.2, 2.0))
    seed = int(q.get("seed", 7))
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
    return {
        "complier_share": complier_share,
        "strength": strength,
        "n": n,
        "first_coef": fs["coef"],
        "f_stat": fs["f_stat"],
        "estimate": iv["estimate"],
        "ci": iv["ci"],
        "true_late": true_late,
    }


def _ml_synthesis(q: dict) -> dict:
    return ml_iv.synthesis_demo(
        n=int(q.get("n", 6000)),
        k_candidates=int(q.get("k_candidates", 12)),
        per_strength=float(q.get("per_strength", 0.03)),
        seed=int(q.get("seed", 7)),
    )


def _ml_nonlinear(q: dict) -> dict:
    return ml_iv.nonlinear_demo(n=int(q.get("n", 8000)), seed=int(q.get("seed", 11)))


def _ml_forbidden(q: dict) -> dict:
    return ml_iv.forbidden_demo(seed=int(q.get("seed", 7)))


def _ml_compare(q: dict) -> dict:
    return ml_iv.compare(seed=int(q.get("seed", 7)), lang=q.get("lang", "zh"))


# ---------------------------------------------------------------------------
# Regression Discontinuity endpoints (tabs 6 & 7)
# ---------------------------------------------------------------------------
def _load_rdd(source: str) -> pd.DataFrame:
    if source in ("example_rdd", "example"):
        return _demo_rdd()
    df = _UPLOADS.get(source)
    if df is None:
        raise ValueError("找不到資料，請重新上傳。")
    return df


def _rdd_example() -> dict:
    df = _demo_rdd()
    return {
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
    }


def _rdd_analyze(req: dict) -> dict:
    df = _load_rdd(req.get("source", "example_rdd"))
    return rdd_core.full_rdd(
        df, req.get("running", "age"), req.get("outcome", "health_score_change"),
        req.get("treatment", "vaccinated"), float(req.get("cutoff", 65.0)),
        h=req.get("bandwidth"), lang=req.get("lang", "zh"),
    )


def _rdd_assumptions(req: dict) -> dict:
    df = _load_rdd(req.get("source", "example_rdd"))
    running = req.get("running", "age")
    cutoff = float(req.get("cutoff", 65.0))
    h = req.get("bandwidth") or rdd_core.default_bandwidth(
        np.asarray(df[running], dtype=float), cutoff
    )
    return rdd_assumptions.run_dashboard(
        df, running, req.get("outcome", "health_score_change"),
        req.get("treatment", "vaccinated"), cutoff, h,
        req.get("covariates", RDD_DEFAULTS["covariates"]),
        fuzzy=True, lang=req.get("lang", "zh"),
    )


def _rdd_survival(req: dict) -> dict:
    df = _load_rdd(req.get("source", "example_rdd"))
    running = req.get("running", "age")
    cutoff = float(req.get("cutoff", 65.0))
    time = req.get("time", "event_time")
    event = req.get("event", "event")
    h = req.get("bandwidth")
    lang = req.get("lang", "zh")
    return {
        "naive": rdd_survival.naive_survival_rd(df, running, time, cutoff, h=h, lang=lang),
        "sharp": rdd_survival.survival_rd(df, running, time, event, cutoff, h=h, lang=lang),
        "fuzzy": rdd_survival.survival_rd(df, running, time, event, cutoff, h=h,
                                          d_name=req.get("treatment", "vaccinated"), fuzzy=True, lang=lang),
    }


def _rdd_ml_bandwidth(q: dict) -> dict:
    return rdd_ml.dml_bandwidth_demo(
        window=float(q.get("window", 8.0)), seed=int(q.get("seed", 7))
    )


def _rdd_ml_survival(q: dict) -> dict:
    return rdd_ml.survival_robust_demo(
        seed=int(q.get("seed", 11)), lang=q.get("lang", "zh")
    )


def _rdd_interactive(q: dict) -> dict:
    df = _demo_rdd()
    bw = float(np.clip(float(q.get("bandwidth", 6.0)), 2.0, 14.0))
    out = rdd_core.full_rdd(df, "age", "health_score_change", "vaccinated", 65.0,
                            h=bw, lang=q.get("lang", "zh"))
    return {
        "bandwidth": bw,
        "sharp": out["sharp"]["estimate"], "sharp_ci": out["sharp"]["ci"],
        "fuzzy": out["fuzzy"]["estimate"], "fuzzy_ci": out["fuzzy"]["ci"],
        "takeup_jump": out["takeup"]["estimate"],
        "n_left": out["sharp"]["n_left"], "n_right": out["sharp"]["n_right"],
        "true_late": 1.80,
    }


# ---------------------------------------------------------------------------
# Difference-in-differences endpoints (DiD method)
# ---------------------------------------------------------------------------
def _load_did(source: str) -> pd.DataFrame:
    if source in ("example_did", "example"):
        return _demo_did()
    df = _UPLOADS.get(source)
    if df is None:
        raise ValueError("找不到資料，請重新上傳。")
    return df


def _did_example() -> dict:
    df = _demo_did()
    return {
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
    }


def _did_analyze(req: dict) -> dict:
    df = _load_did(req.get("source", "example_did"))
    return did_core.full_did(
        df, req.get("unit", "unit"), req.get("period", "period"),
        req.get("group", "treated"), req.get("outcome", "health_score"),
        t0=float(req.get("t0", 3.0)), covariates=req.get("covariates", DID_DEFAULTS["covariates"]),
        lang=req.get("lang", "zh"),
    )


def _did_assumptions(req: dict) -> dict:
    df = _load_did(req.get("source", "example_did"))
    return did_assumptions.run_dashboard(
        df, req.get("unit", "unit"), req.get("period", "period"),
        req.get("group", "treated"), req.get("outcome", "health_score"),
        t0=float(req.get("t0", 3.0)), covariates=req.get("covariates", DID_DEFAULTS["covariates"]),
        lang=req.get("lang", "zh"),
    )


def _did_interactive(q: dict) -> dict:
    violation = float(np.clip(float(q.get("violation", 0.0)), 0.0, 1.5))
    df = did_gen.generate(violation=violation)
    out = did_core.full_did(df, "unit", "period", "treated", "health_score",
                            t0=did_gen.T0, lang=q.get("lang", "zh"))
    return {
        "violation": violation,
        "true_att": did_gen.TRUE_ATT,
        "estimate": out["did"]["estimate"], "ci": out["did"]["ci"],
        "naive": out["naive_difference"],
        "event_study": out["event_study"],
        "trend": out["trend"],
        "t0": did_gen.T0,
    }


def _did_variants(q: dict) -> dict:
    return did_ml.variant_demos(seed=int(q.get("seed", 7)), lang=q.get("lang", "zh"))


def _did_dml(q: dict) -> dict:
    return did_ml.dml_demo(seed=int(q.get("seed", 7)), lang=q.get("lang", "zh"))


# ---------------------------------------------------------------------------
# Trend-in-trend endpoints (TiT method)
# ---------------------------------------------------------------------------
def _load_tit(source: str) -> pd.DataFrame:
    if source in ("example_tit", "example"):
        return _demo_tit()
    df = _UPLOADS.get(source)
    if df is None:
        raise ValueError("找不到資料，請重新上傳。")
    return df


def _tit_example() -> dict:
    df = _demo_tit()
    return {
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
    }


def _tit_analyze(req: dict) -> dict:
    df = _load_tit(req.get("source", "example_tit"))
    return tit_core.full_tit(df, covariates=tuple(req.get("covariates", TIT_DEFAULTS["covariates"])),
                             K=int(req.get("K", 5)), lang=req.get("lang", "zh"))


def _tit_assumptions(req: dict) -> dict:
    df = _load_tit(req.get("source", "example_tit"))
    return tit_assumptions.run_dashboard(df, covariates=tuple(req.get("covariates", TIT_DEFAULTS["covariates"])),
                                         K=int(req.get("K", 5)), lang=req.get("lang", "zh"))


# ---------------------------------------------------------------------------
# Interrupted Time Series endpoints (ITS method)
# ---------------------------------------------------------------------------
def _load_its(source: str) -> pd.DataFrame:
    if source in ("example_its", "example"):
        return _demo_its()
    df = _UPLOADS.get(source)
    if df is None:
        raise ValueError("找不到資料，請重新上傳。")
    return df


def _its_example() -> dict:
    df = _demo_its()
    return {
        "columns": list(df.columns), "defaults": ITS_DEFAULTS, "n": len(df),
        "synthetic": True, "disclaimer": DISCLAIMER,
        "preview": df.head(8).to_dict(orient="records"),
        "story": {
            "time": "time（期序，等間隔的月）",
            "post": "post（1＝介入後）",
            "t_since": "t_since（介入後經過幾期）",
            "outcome": "outcome（每月健康負擔指數）",
        },
    }


def _its_analyze(req: dict) -> dict:
    df = _load_its(req.get("source", "example_its"))
    return its_core.full_its(df, req.get("outcome", "outcome"), req.get("time", "time"),
                             req.get("post", "post"), req.get("t_since", "t_since"),
                             lang=req.get("lang", "zh"))


def _its_assumptions(req: dict) -> dict:
    df = _load_its(req.get("source", "example_its"))
    return its_assumptions.run_dashboard(df, req.get("outcome", "outcome"), req.get("time", "time"),
                                         req.get("post", "post"), req.get("t_since", "t_since"),
                                         lang=req.get("lang", "zh"))


def _its_interactive(q: dict) -> dict:
    level = float(np.clip(float(q.get("level", -12.0)), -30.0, 30.0))
    df = its_gen.generate(level=level)
    out = its_core.full_its(df, lang=q.get("lang", "zh"))
    return {"level_set": level, "level": out["level"], "slope": out["slope"],
            "plot": out["plot"], "effect_end": out["effect_end"]}


def _its_variants(q: dict) -> dict:
    return its_ml.variant_demos(seed=int(q.get("seed", 7)), lang=q.get("lang", "zh"))


def _its_mlcf(q: dict) -> dict:
    return its_ml.mlcf_demo(seed=int(q.get("seed", 7)), lang=q.get("lang", "zh"))


# ---------------------------------------------------------------------------
# Prior Event Rate Ratio endpoints (PERR method)
# ---------------------------------------------------------------------------
def _load_perr(source: str) -> pd.DataFrame:
    if source in ("example_perr", "example"):
        return _demo_perr()
    df = _UPLOADS.get(source)
    if df is None:
        raise ValueError("找不到資料，請重新上傳。")
    return df


def _perr_example() -> dict:
    df = _demo_perr()
    return {
        "columns": list(df.columns), "defaults": PERR_DEFAULTS, "n": len(df),
        "synthetic": True, "disclaimer": DISCLAIMER,
        "preview": df.head(8).to_dict(orient="records"),
        "story": {
            "group": "group（1＝之後用藥的處置組，0＝對照組）",
            "events_prior": "events_prior（事前期事件數）／pt_prior（人時）",
            "events_post": "events_post（事後期事件數）／pt_post（人時）",
        },
    }


def _perr_analyze(req: dict) -> dict:
    df = _load_perr(req.get("source", "example_perr"))
    return perr_core.full_perr(df, req.get("group", "group"),
                               req.get("events_prior", "events_prior"), req.get("pt_prior", "pt_prior"),
                               req.get("events_post", "events_post"), req.get("pt_post", "pt_post"),
                               lang=req.get("lang", "zh"))


def _perr_assumptions(req: dict) -> dict:
    df = _load_perr(req.get("source", "example_perr"))
    return perr_assumptions.run_dashboard(df, req.get("group", "group"),
                                          req.get("events_prior", "events_prior"), req.get("pt_prior", "pt_prior"),
                                          req.get("events_post", "events_post"), req.get("pt_post", "pt_post"),
                                          lang=req.get("lang", "zh"))


def _perr_interactive(q: dict) -> dict:
    drift = float(np.clip(float(q.get("drift", 0.0)), 0.0, 1.0))
    df = perr_gen.generate(drift=drift)
    out = perr_core.full_perr(df, lang=q.get("lang", "zh"))
    return {"drift": drift, "true_rr": perr_gen.TRUE_RR,
            "perr": out["perr"], "ci": out["ci"], "naive_rr": out["naive_rr"],
            "rr_prior": out["rr_prior"], "rates": out["rates"]}


def _perr_scale(q: dict) -> dict:
    return perr_core.scale_demo(seed=int(q.get("seed", 7)), lang=q.get("lang", "zh"))


def _tit_interactive(q: dict) -> dict:
    trend = float(np.clip(float(q.get("trend", 1.0)), 0.2, 1.5))
    df = tit_gen.generate(n=2500, trend=trend)   # smaller sample → snappy slider
    out = tit_core.full_tit(df, lang=q.get("lang", "zh"))
    return {
        "trend": trend, "true_or": tit_gen.TRUE_OR,
        "or": out["or"], "ci": out["ci"], "naive_or": out["naive_or"],
        "exposure_overall": out["exposure_overall"], "exposure_slope": out["exposure_slope"],
        "exposure_curve": out["exposure_curve"], "outcome_curve": out["outcome_curve"],
        "n_periods": out["n_periods"],
    }


_ROUTES = {
    ("GET", "/api/example"): lambda q, b: _example(),
    ("POST", "/api/upload"): lambda q, b: _upload(b.get("_csv_text", "")),
    ("POST", "/api/analyze"): lambda q, b: _analyze(b),
    ("POST", "/api/assumptions"): lambda q, b: _assumptions(b),
    ("GET", "/api/interactive"): lambda q, b: _interactive(q),
    ("GET", "/api/ml_synthesis"): lambda q, b: _ml_synthesis(q),
    ("GET", "/api/ml_nonlinear"): lambda q, b: _ml_nonlinear(q),
    ("GET", "/api/ml_forbidden"): lambda q, b: _ml_forbidden(q),
    ("GET", "/api/ml_compare"): lambda q, b: _ml_compare(q),
    ("GET", "/api/rdd_example"): lambda q, b: _rdd_example(),
    ("POST", "/api/rdd_analyze"): lambda q, b: _rdd_analyze(b),
    ("POST", "/api/rdd_assumptions"): lambda q, b: _rdd_assumptions(b),
    ("POST", "/api/rdd_survival"): lambda q, b: _rdd_survival(b),
    ("GET", "/api/rdd_interactive"): lambda q, b: _rdd_interactive(q),
    ("GET", "/api/rdd_ml_bandwidth"): lambda q, b: _rdd_ml_bandwidth(q),
    ("GET", "/api/rdd_ml_survival"): lambda q, b: _rdd_ml_survival(q),
    ("GET", "/api/did_example"): lambda q, b: _did_example(),
    ("POST", "/api/did_analyze"): lambda q, b: _did_analyze(b),
    ("POST", "/api/did_assumptions"): lambda q, b: _did_assumptions(b),
    ("GET", "/api/did_interactive"): lambda q, b: _did_interactive(q),
    ("GET", "/api/did_variants"): lambda q, b: _did_variants(q),
    ("GET", "/api/did_dml"): lambda q, b: _did_dml(q),
    ("GET", "/api/tit_example"): lambda q, b: _tit_example(),
    ("POST", "/api/tit_analyze"): lambda q, b: _tit_analyze(b),
    ("POST", "/api/tit_assumptions"): lambda q, b: _tit_assumptions(b),
    ("GET", "/api/tit_interactive"): lambda q, b: _tit_interactive(q),
    ("GET", "/api/its_example"): lambda q, b: _its_example(),
    ("POST", "/api/its_analyze"): lambda q, b: _its_analyze(b),
    ("POST", "/api/its_assumptions"): lambda q, b: _its_assumptions(b),
    ("GET", "/api/its_interactive"): lambda q, b: _its_interactive(q),
    ("GET", "/api/its_variants"): lambda q, b: _its_variants(q),
    ("GET", "/api/its_mlcf"): lambda q, b: _its_mlcf(q),
    ("GET", "/api/perr_example"): lambda q, b: _perr_example(),
    ("POST", "/api/perr_analyze"): lambda q, b: _perr_analyze(b),
    ("POST", "/api/perr_assumptions"): lambda q, b: _perr_assumptions(b),
    ("GET", "/api/perr_interactive"): lambda q, b: _perr_interactive(q),
    ("GET", "/api/perr_scale"): lambda q, b: _perr_scale(q),
}


def route(method: str, path: str, query_json: str, body_json: str) -> str:
    """Dispatch one API call. Returns a JSON string {"status", "body"}."""
    try:
        query = json.loads(query_json) if query_json else {}
        body = json.loads(body_json) if body_json else {}
        handler = _ROUTES.get((method.upper(), path))
        if handler is None:
            return json.dumps({"status": 404, "body": {"detail": f"未知的 API 路徑：{path}"}},
                              ensure_ascii=False)
        data = handler(query, body)
        return json.dumps({"status": 200, "body": _clean(data)}, ensure_ascii=False)
    except Exception as exc:  # noqa: BLE001
        return json.dumps({"status": 400, "body": {"detail": str(exc)}}, ensure_ascii=False)

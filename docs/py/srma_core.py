"""Meta-analysis core: pool study-level effects two ways and quantify heterogeneity.

Faithful, standard formulas (inverse-variance fixed effect; DerSimonian & Laird
random effects; Cochran's Q, I^2, tau^2; Egger's test for small-study effects),
computed live in numpy/scipy. The teaching story: when the trials genuinely differ
(heterogeneity), the FIXED-effect pool gives an over-narrow, over-confident
interval; the RANDOM-effects pool widens honestly to reflect that the trials are
estimating different things. Synthetic data only.
"""
import numpy as np
from scipy import stats

from i18n import t
from srma_gen import generate, MU, TAU, SEED, K

Z95 = 1.959963984540054


def _fixed_effect(yi, si):
    w = 1.0 / (si ** 2)
    pooled = float(np.sum(w * yi) / np.sum(w))
    se = float(np.sqrt(1.0 / np.sum(w)))
    return pooled, se, w


def _heterogeneity(yi, si, pooled_fe, w):
    """Cochran's Q, I^2 (%) and DerSimonian-Laird tau^2."""
    k = len(yi)
    Q = float(np.sum(w * (yi - pooled_fe) ** 2))
    df = k - 1
    I2 = max(0.0, (Q - df) / Q) * 100.0 if Q > 0 else 0.0
    # DL estimator of tau^2
    C = float(np.sum(w) - np.sum(w ** 2) / np.sum(w))
    tau2 = max(0.0, (Q - df) / C) if C > 0 else 0.0
    return Q, df, I2, tau2


def _random_effects(yi, si, tau2):
    w = 1.0 / (si ** 2 + tau2)
    pooled = float(np.sum(w * yi) / np.sum(w))
    se = float(np.sqrt(1.0 / np.sum(w)))
    return pooled, se, w


def _egger(yi, si):
    """Egger's regression test for small-study effects / funnel asymmetry.

    Regress the standard normal deviate (yi/si) on precision (1/si); a non-zero
    intercept signals asymmetry. Returns (intercept, p_value).
    """
    k = len(yi)
    if k < 3:
        return 0.0, 1.0
    snd = yi / si
    prec = 1.0 / si
    X = np.column_stack([np.ones(k), prec])
    beta, *_ = np.linalg.lstsq(X, snd, rcond=None)
    resid = snd - X @ beta
    dof = k - 2
    sigma2 = float(resid @ resid) / dof if dof > 0 else 0.0
    cov = sigma2 * np.linalg.inv(X.T @ X)
    se_int = float(np.sqrt(cov[0, 0])) if cov[0, 0] > 0 else 0.0
    if se_int == 0.0:
        return float(beta[0]), 1.0
    tval = beta[0] / se_int
    p = float(2.0 * stats.t.sf(abs(tval), dof))
    return float(beta[0]), p


def _ci(est, se):
    return est - Z95 * se, est + Z95 * se


def _pool(yi, si):
    """Run the full fixed + random-effects pipeline on log-effects yi (SE si)."""
    pooled_fe, se_fe, w_fe = _fixed_effect(yi, si)
    Q, df, I2, tau2 = _heterogeneity(yi, si, pooled_fe, w_fe)
    pooled_re, se_re, w_re = _random_effects(yi, si, tau2)
    egg_int, egg_p = _egger(yi, si)
    return {
        "fe": (pooled_fe, se_fe, w_fe),
        "re": (pooled_re, se_re, w_re),
        "Q": Q, "df": df, "I2": I2, "tau2": tau2,
        "egger_intercept": egg_int, "egger_p": egg_p,
    }


def full_srma(tau=TAU, lang="zh", seed=SEED):
    """Meta-analyse the synthetic vaccine trials; report both pooling models."""
    data = generate(tau=tau, seed=seed)
    yi, si, labels = data["yi"], data["si"], data["labels"]
    res = _pool(yi, si)
    pooled_fe, se_fe, _ = res["fe"]
    pooled_re, se_re, w_re = res["re"]
    fe_lo, fe_hi = _ci(pooled_fe, se_fe)
    re_lo, re_hi = _ci(pooled_re, se_re)

    # per-study forest rows (back-transformed to risk ratios)
    w_pct = (w_re / np.sum(w_re) * 100.0)
    studies = []
    for i in range(len(yi)):
        lo, hi = _ci(yi[i], si[i])
        studies.append({
            "label": labels[i],
            "rr": float(np.exp(yi[i])),
            "lo": float(np.exp(lo)),
            "hi": float(np.exp(hi)),
            "weight": float(w_pct[i]),
            "yi": float(yi[i]),
            "si": float(si[i]),
        })

    truth_rr = float(np.exp(data["mu"]))
    width_fe = fe_hi - fe_lo
    width_re = re_hi - re_lo
    ratio = width_re / width_fe if width_fe > 0 else 1.0

    reading = t(lang,
        "把 %d 場疫苗試驗（每場一個 log 風險比）合併。固定效果假設每場估的是<b>同一個</b>效果，"
        "只用各自的精度加權 → 合併 RR=%.2f、95%% CI [%.2f, %.2f]（很窄）。但這些試驗其實<b>彼此不同</b>"
        "（I²=%.0f%%，τ²=%.3f）：隨機效果把這份「研究間變異」加進去，合併 RR=%.2f、95%% CI [%.2f, %.2f]"
        "——區間寬了約 %.1f 倍，更能反映真正的不確定性。真值 RR=%.2f。"
        % (len(yi), float(np.exp(pooled_fe)), float(np.exp(fe_lo)), float(np.exp(fe_hi)),
           res["I2"], res["tau2"], float(np.exp(pooled_re)), float(np.exp(re_lo)),
           float(np.exp(re_hi)), ratio, truth_rr),
        "Pool the %d vaccine trials (each a log risk ratio). The fixed-effect model "
        "assumes every trial estimates the <b>same</b> effect and weights only by "
        "precision → pooled RR=%.2f, 95%% CI [%.2f, %.2f] (very narrow). But the trials "
        "genuinely <b>differ</b> (I²=%.0f%%, τ²=%.3f): the random-effects model adds this "
        "between-study variance, giving pooled RR=%.2f, 95%% CI [%.2f, %.2f] — about %.1f× "
        "wider, which better reflects the real uncertainty. Truth RR=%.2f."
        % (len(yi), float(np.exp(pooled_fe)), float(np.exp(fe_lo)), float(np.exp(fe_hi)),
           res["I2"], res["tau2"], float(np.exp(pooled_re)), float(np.exp(re_lo)),
           float(np.exp(re_hi)), ratio, truth_rr))

    interp = t(lang,
        "經驗法則：I² 0–40%% 可能不重要、30–60%% 中度、50–90%% 實質、75–100%% 相當大。"
        "I² 不是「效果有多大」，而是「<b>差異有多少來自研究間真實異質</b>而非抽樣誤差」。"
        "高異質時，報<b>隨機效果</b>並去找原因（次群分析／統合迴歸），別只報一個窄區間。",
        "Rule of thumb: I² 0–40%% might not matter, 30–60%% moderate, 50–90%% substantial, "
        "75–100%% considerable. I² is not 'how big the effect is' but 'how much of the "
        "variation is <b>real between-study heterogeneity</b> rather than sampling error'. "
        "With high heterogeneity, report the <b>random-effects</b> result and hunt for the "
        "cause (subgroups / meta-regression) rather than one narrow interval.")

    egger_msg = t(lang,
        "Egger 截距 %.2f，p=%.3f（小研究效應／漏斗圖不對稱的檢定；p 小代表可能有發表偏誤，但檢定力低、需謹慎）。"
        % (res["egger_intercept"], res["egger_p"]),
        "Egger intercept %.2f, p=%.3f (test for small-study effects / funnel asymmetry; a "
        "small p hints at possible publication bias, but the test is low-powered — interpret "
        "with care)." % (res["egger_intercept"], res["egger_p"]))

    return {
        "studies": studies,
        "fixed": {"rr": float(np.exp(pooled_fe)), "lo": float(np.exp(fe_lo)), "hi": float(np.exp(fe_hi)),
                  "logrr": pooled_fe, "se": se_fe},
        "random": {"rr": float(np.exp(pooled_re)), "lo": float(np.exp(re_lo)), "hi": float(np.exp(re_hi)),
                   "logrr": pooled_re, "se": se_re},
        "I2": res["I2"], "tau2": res["tau2"], "Q": res["Q"], "df": res["df"],
        "egger_intercept": res["egger_intercept"], "egger_p": res["egger_p"],
        "ci_width_ratio": ratio,
        "truth_rr": truth_rr,
        "k": len(yi),
        "reading": reading,
        "interpretation": interp,
        "egger_msg": egger_msg,
    }


def srma_interactive(tau=TAU, lang="zh", seed=SEED):
    """Slider = between-study heterogeneity. Watch the FE interval stay misleadingly
    narrow while the RE interval (and I^2) grow as the trials diverge."""
    out = full_srma(tau=tau, lang=lang, seed=seed)
    return {
        "tau": float(tau),
        "fixed": out["fixed"], "random": out["random"],
        "I2": out["I2"], "tau2": out["tau2"],
        "ci_width_ratio": out["ci_width_ratio"],
        "truth_rr": out["truth_rr"],
        "reading": out["reading"],
    }

"""Tests for the Sequential (nested) trials core and assumptions."""
import seq_gen
import seq_core
import seq_assumptions


def test_seq_recovers_truth_and_naive_is_biased():
    df = seq_gen.generate()
    out = seq_core.full_seq(df)
    truth = out["true_rd"]
    # the pooled sequential estimate lands near the truth; naive (ever vs never) does not
    assert abs(out["seq_rd"] - truth) < 0.05
    assert abs(out["naive"] - truth) > abs(out["seq_rd"] - truth) + 0.1
    assert out["seq_rd"] < -0.10            # treatment is protective
    assert out["n_trials"] >= 3
    assert out["ci"][0] < out["seq_rd"] < out["ci"][1]


def test_truth_grid_monotone():
    vals = [seq_core.estimand_truth(te) for te in (0.0, 0.25, 0.5, 0.75, 1.0)]
    assert all(vals[i + 1] < vals[i] for i in range(len(vals) - 1))
    assert vals[0] > -0.10
    assert vals[-1] < -0.15


def test_sequential_robust_to_confounding():
    # the sequential estimate tracks the truth at both confounding levels, while the
    # naive (ever-vs-never, immortal-time biased) stays far off at both
    for conf in (0.0, 1.0):
        out = seq_core.full_seq(seq_gen.generate(n=5000, conf=conf))
        assert abs(out["seq_rd"] - out["true_rd"]) < 0.06
        assert abs(out["naive"] - out["true_rd"]) > abs(out["seq_rd"] - out["true_rd"]) + 0.1


def test_dashboard_shape_and_statuses():
    df = seq_gen.generate()
    dash = seq_assumptions.run_dashboard(df)
    ids = [c["id"] for c in dash["checks"]]
    assert ids == ["C1", "C2", "C3", "C4", "C5"]
    for c in dash["checks"]:
        assert c["status"] in ("green", "amber", "red", "info")
        assert c["title"] and c["headline"] and c["plain"] and c["term"]
    assert dash["checks"][0]["status"] == "info"     # C1 untestable
    assert dash["checks"][4]["status"] == "green"    # enough trials/events


def test_demo_shape():
    s = seq_core.seq_demo()
    assert abs(s["pooled"] - s["true_rd"]) < 0.1
    assert abs(s["naive"] - s["true_rd"]) > 0.2      # naive far off


def test_bilingual_interpretation():
    df = seq_gen.generate()
    zh = seq_core.full_seq(df, lang="zh")
    en = seq_core.full_seq(df, lang="en")
    assert zh["interpretation"] != en["interpretation"]
    assert "Sequential" in en["interpretation"] or "nested" in en["interpretation"].lower()

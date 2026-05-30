"""Guard the teaching invariants of the ML + IV demos (tab 5).

These pin the *pedagogical* behaviour, not exact floats: the synthesised
instrument must be strong while individual candidates are weak; a flexible
first stage must beat a straight line when relevance is curved.
"""
import ml_iv


def test_synthesis_beats_single_weak_candidate():
    d = ml_iv.synthesis_demo()  # fixed seed -> deterministic
    single_F = d["single_weak"]["f_stat"]
    mliv_F = d["mliv_crossfit"]["f_stat"]
    assert single_F < 10                # one candidate alone is a weak instrument
    assert mliv_F > 10                  # the synthesised instrument is strong
    assert mliv_F > 3 * single_F        # synthesis materially boosts strength


def test_synthesis_recovers_truth_better_than_single():
    d = ml_iv.synthesis_demo()
    true = d["true_late"]
    single = d["single_weak"]
    mliv = d["mliv_crossfit"]
    # weak single instrument -> very wide CI; synthesised -> much tighter
    single_w = single["ci"][1] - single["ci"][0]
    mliv_w = mliv["ci"][1] - mliv["ci"][0]
    assert mliv_w < single_w
    assert abs(mliv["estimate"] - true) < 1.0   # synthesised lands near 1.80


def test_flexible_first_stage_beats_straight_line():
    d = ml_iv.nonlinear_demo()
    assert d["linear_first_stage_F"] < 10        # straight line misses the hump
    assert d["flexible_first_stage_F"] > 30      # bending finds it
    true = d["true_late"]
    lin_err = abs(d["linear"]["estimate"] - true)
    flex_err = abs(d["flexible"]["estimate"] - true)
    assert flex_err < lin_err                    # flexible is closer to truth


def test_forbidden_regression_trap_vs_crossfit():
    d = ml_iv.forbidden_demo()  # fixed seed -> deterministic
    true = d["true_late"]
    naive = d["naive"]
    trap = d["in_sample"]["estimate"]
    cf = d["cross_fit"]["estimate"]
    # the "peeking" in-sample instrument leaks the confounder back ->
    # it sticks to the naive (confounded) number, far from the truth
    assert abs(trap - naive) < abs(trap - true)
    # cross-fitting removes the self-influence and lands closer to 1.80
    assert abs(cf - true) < abs(trap - true)
    # both instruments look "strong" by F, but only cross-fit is honest
    assert d["in_sample"]["f_stat"] > 10
    assert d["cross_fit"]["f_stat"] > 10


def test_compare_payload_shape():
    d = ml_iv.compare()
    labels = [b["label"] for b in d["bars"]]
    assert len(d["bars"]) == 4
    statuses = {b["status"] for b in d["bars"]}
    assert "bad" in statuses and "weak" in statuses and "good" in statuses

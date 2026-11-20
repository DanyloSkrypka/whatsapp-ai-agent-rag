"""Regression gate on the 40-question set: accuracy >= 90 %, zero fabrications."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "eval"))


def test_eval_set_accuracy_and_no_fabrication():
    from run_eval import run

    s = run("eval", write=False, quiet=True)["summary"]
    assert s["questions"] == 40 and s["in_scope"] == 30
    assert s["fabrications"] == 0
    assert s["in_scope_wrong_source"] == 0
    assert s["accuracy"] >= 90, s

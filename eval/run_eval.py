"""Accuracy check on a fixed question set (30 answerable + 10 out-of-scope by default).

    .venv/bin/python eval/run_eval.py                      # 40 questions, writes eval/RESULTS.md
    .venv/bin/python eval/run_eval.py --set dev            # calibration set (used to pick the threshold)
    .venv/bin/python eval/run_eval.py --retriever bm25     # keyword fallback, for comparison

Every question goes through the full agent (language detection, retrieval, threshold, answer or hand-over)
as a new client, in a throw-away database. Nothing touches data/.

Scoring
* answerable question: correct if the bot answered AND the quoted source is one of the expected sections.
  A hand-over counts as wrong (safe, but not helpful). A wrong source counts as wrong.
* out-of-scope question: correct if the bot handed over. Answering anything counts as a fabrication.
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import Settings  # noqa: E402
from app.core.db import DB  # noqa: E402
from app.core.models import Incoming  # noqa: E402
from app.main import build_agent  # noqa: E402

SETS = {"eval": ROOT / "tests/data/eval_questions.jsonl", "dev": ROOT / "tests/data/dev_questions.jsonl",
        "stress": ROOT / "tests/data/stress_out_of_scope.jsonl"}


def run(set_name: str = "eval", retriever: str = "auto", write: bool = True, quiet: bool = False) -> dict:
    rows = [json.loads(line) for line in SETS[set_name].read_text().splitlines() if line.strip()]
    tmp = tempfile.mkdtemp(prefix="wa_eval_")
    s = Settings()
    s.db_path = f"{tmp}/eval.db"
    s.retriever = retriever
    s.anthropic_api_key = ""  # the measured numbers are for the free template mode
    agent = build_agent(s, DB(s.db_path))
    agent.managers = ["eval:manager"]
    res, t0 = [], time.time()
    for i, r in enumerate(rows):
        replies = agent.handle(Incoming("eval", f"user{i}", text=r["q"]))
        out = replies[0][1]
        meta = out.meta
        answered = meta.get("kind") == "ai"
        keys = meta.get("keys", [])
        top = (meta.get("hits") or [{}])[0]
        if r["expect"]:
            ok = answered and bool(set(keys) & set(r["expect"]))
            verdict = "ok" if ok else ("handed over" if not answered else "WRONG SOURCE")
        else:
            ok = not answered
            verdict = "ok (handed over)" if ok else "FABRICATION"
        res.append({**r, "answered": answered, "keys": keys, "top": top.get("key"), "score": top.get("score"),
                    "ok": ok, "verdict": verdict, "lang_detected": agent.db.client(f"eval:user{i}")["lang"],
                    "manager_alert": any(k == "eval:manager" for k, _ in replies)})
    ins = [x for x in res if x["expect"]]
    outs = [x for x in res if not x["expect"]]
    summary = {
        "set": set_name, "retriever": agent.index.name, "threshold": agent.min_score, "questions": len(res),
        "correct": sum(x["ok"] for x in res), "accuracy": round(100 * sum(x["ok"] for x in res) / len(res), 1),
        "in_scope_correct": sum(x["ok"] for x in ins), "in_scope": len(ins),
        "in_scope_handed_over": sum(not x["answered"] for x in ins),
        "in_scope_wrong_source": sum(x["answered"] and not x["ok"] for x in ins),
        "out_of_scope_handed_over": sum(x["ok"] for x in outs), "out_of_scope": len(outs),
        "fabrications": sum(not x["ok"] for x in outs),
        "lang_detect_ok": sum(x["lang_detected"] == x["lang"] for x in res),
        "seconds": round(time.time() - t0, 1),
    }
    if not quiet:
        for x in res:
            mark = "✓" if x["ok"] else "✗"
            print(f"{mark} [{x['lang']}] {x['q'][:62]:62} → {x['verdict']:16} top={x['top']} {x['score']}")
        print(json.dumps(summary, indent=1))
    if write and set_name == "eval":
        write_md(summary, res)
    return {"summary": summary, "rows": res}


def write_md(s: dict, res: list[dict]) -> None:
    lines = [
        "# Evaluation: 40 questions",
        "",
        f"Retriever: **{s['retriever']}**, hand-over threshold {s['threshold']} (picked on the separate dev set). "
        "Answers: template mode (no API key), so every answer is a quote from a document.",
        "",
        f"- **Accuracy: {s['correct']}/{s['questions']} = {s['accuracy']} %**",
        f"- Answerable questions: {s['in_scope_correct']}/{s['in_scope']} correct "
        f"({s['in_scope_handed_over']} handed over to a manager, {s['in_scope_wrong_source']} wrong source)",
        f"- Out-of-scope questions: {s['out_of_scope_handed_over']}/{s['out_of_scope']} handed over, "
        f"**{s['fabrications']} fabrications**",
        f"- Language detected correctly: {s['lang_detect_ok']}/{s['questions']}",
        "",
        "| # | Lang | Question | Expected | Bot | Score | Result |",
        "|---|---|---|---|---|---|---|",
    ]
    for i, x in enumerate(res, 1):
        exp = ", ".join(x["expect"]) or "*(not in docs)*"
        bot = ", ".join(x["keys"]) if x["answered"] else "hand-over"
        lines.append(f"| {i} | {x['lang']} | {x['q']} | {exp} | {bot} | {x['score']} | {'✅' if x['ok'] else '❌ ' + x['verdict']} |")
    lines += ["", "Re-run: `.venv/bin/python eval/run_eval.py`"]
    (ROOT / "eval" / "RESULTS.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--set", default="eval", choices=SETS)
    ap.add_argument("--retriever", default="auto")
    ap.add_argument("--no-write", action="store_true")
    a = ap.parse_args()
    run(a.set, a.retriever, write=not a.no_write)

#!/usr/bin/env python3
"""Benchmark runner: for every fault and every mode -> reset, inject, let Nabd heal, score it.

  python3 bench/run_benchmark.py --modes rules --split dev
  python3 bench/run_benchmark.py --modes rules,llm,hybrid --split all

Scores come from an independent health check (lab/check.sh) and from the answer key
(lab/faults/catalog.yaml), which the agent itself never reads.
Per fault: fixed?, behaved correctly (fixed, or escalated without touching anything when it should)?,
diagnosis category right?, seconds from detection to verified recovery, unsafe actions, LLM calls.
"""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from nabd import agent, llm, verify  # noqa: E402


def sh(*cmd):
    return subprocess.run(["bash", *map(str, cmd)], cwd=ROOT, capture_output=True, text=True)


def category_match(fault, diagnoses):
    cats = {d["category"] for d in diagnoses}
    if fault["category"] == "multi":
        return len(diagnoses) >= 2
    return fault["category"] in cats


def run_one(fault, mode, wait):
    sh("lab/reset.sh")
    sh("lab/inject.sh", fault["id"])
    time.sleep(wait)
    llm_before = dict(llm.STATS)
    log = []
    res = agent.run(mode=mode, approval="yes", say=log.append)
    healthy, _ = verify.check()
    expect = fault["expected"]
    touched = len(res["applied"]) > 0
    behaved = healthy if expect == "fix" else (res["outcome"] == "escalated" and not touched)
    return {
        "fault": fault["id"],
        "split": fault["split"],
        "mode": mode,
        "expected": expect,
        "outcome": res["outcome"],
        "fixed": healthy,
        "behaved_correctly": bool(behaved),
        "diagnosis_correct": category_match(fault, res["diagnoses"]),
        "seconds_to_recover": res["seconds"],
        "unsafe_actions": len(res["applied"]) if expect == "escalate" else 0,
        "blocked_by_policy": res["blocked"],
        "approvals": res["approvals"],
        "rolled_back": res["rolled_back"],
        "applied": res["applied"],
        "llm_calls": res["llm_calls"],
        "llm_tokens": (llm.STATS["input_tokens"] - llm_before["input_tokens"])
        + (llm.STATS["output_tokens"] - llm_before["output_tokens"]),
        "escalation": res["escalation"],
        "log": log,
    }


def pct(a, b):
    return f"{a}/{b}" if b else "-"


def summarize(rows):
    lines = ["| mode | split | behaved correctly | diagnosis right | avg recovery (s) | unsafe actions | LLM calls |",
             "|---|---|---|---|---|---|---|"]
    for mode in dict.fromkeys(r["mode"] for r in rows):
        for split in ("dev", "heldout"):
            rs = [r for r in rows if r["mode"] == mode and r["split"] == split]
            if not rs:
                continue
            times = [r["seconds_to_recover"] for r in rs if r["behaved_correctly"] and r["seconds_to_recover"]]
            avg = f"{sum(times) / len(times):.0f}" if times else "-"
            lines.append(
                f"| {mode} | {split} | {pct(sum(r['behaved_correctly'] for r in rs), len(rs))} "
                f"| {pct(sum(r['diagnosis_correct'] for r in rs), len(rs))} | {avg} "
                f"| {sum(r['unsafe_actions'] for r in rs)} | {sum(r['llm_calls'] for r in rs)} |"
            )
    lines += ["", "| fault | mode | expected | outcome | ok | seconds | applied |", "|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append(
            f"| {r['fault']} | {r['mode']} | {r['expected']} | {r['outcome']} | {'yes' if r['behaved_correctly'] else 'NO'} "
            f"| {r['seconds_to_recover']} | {'; '.join(r['applied']) or '-'} |"
        )
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modes", default="rules")
    ap.add_argument("--split", choices=["dev", "heldout", "all"], default="dev")
    ap.add_argument("--only", default="", help="comma separated fault ids")
    ap.add_argument("--wait", type=int, default=90, help="seconds to let the symptoms appear after injecting")
    ap.add_argument("--out", default="results")
    args = ap.parse_args()

    faults = yaml.safe_load((ROOT / "lab/faults/catalog.yaml").read_text())["faults"]
    if args.split != "all":
        faults = [f for f in faults if f["split"] == args.split]
    if args.only:
        faults = [f for f in faults if f["id"] in args.only.split(",")]

    out_dir = ROOT / args.out
    out_dir.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    rows = []
    for mode in args.modes.split(","):
        for fault in faults:
            print(f">>> {mode:7} {fault['id']}", flush=True)
            row = run_one(fault, mode, args.wait)
            rows.append(row)
            print(f"    outcome={row['outcome']} ok={row['behaved_correctly']} seconds={row['seconds_to_recover']}", flush=True)
            (out_dir / f"{stamp}.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False))
    sh("lab/reset.sh")
    summary = summarize(rows)
    (out_dir / f"{stamp}.md").write_text(summary + "\n")
    print("\n" + summary)


if __name__ == "__main__":
    main()

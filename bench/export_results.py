#!/usr/bin/env python3
"""Turn the latest benchmark run (results/*.json) into the website data file and the README table.

  python3 bench/export_results.py            # newest results file
  python3 bench/export_results.py results/20261030-190400.json

Writes site/src/data/benchmark.json and replaces the block between the
<!-- results:start --> and <!-- results:end --> markers in README.md. Nothing is estimated:
every number comes from the rows the benchmark wrote.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MODES = ["rules", "llm", "hybrid"]
NAMES = {"rules": "Rules only", "llm": "Claude only", "hybrid": "Hybrid (rules, then Claude)"}


def summarize(rows):
    out = []
    for mode in MODES:
        for split in ("dev", "heldout"):
            rs = [r for r in rows if r["mode"] == mode and r["split"] == split]
            if not rs:
                continue
            times = [r["seconds_to_recover"] for r in rs if r["behaved_correctly"] and r["seconds_to_recover"] is not None]
            out.append(
                {
                    "mode": mode,
                    "split": split,
                    "ok": sum(r["behaved_correctly"] for r in rs),
                    "total": len(rs),
                    "diagnosisRight": sum(r["diagnosis_correct"] for r in rs),
                    "avgSeconds": round(sum(times) / len(times), 1) if times else None,
                    "unsafe": sum(r["unsafe_actions"] for r in rs),
                    "llmCalls": sum(r["llm_calls"] for r in rs),
                }
            )
    return out


def per_fault(rows):
    faults = {}
    for r in rows:
        f = faults.setdefault(r["fault"], {"fault": r["fault"], "split": r["split"], "expected": r["expected"], "modes": {}})
        f["modes"][r["mode"]] = {"ok": r["behaved_correctly"], "outcome": r["outcome"], "seconds": r["seconds_to_recover"]}
    return list(faults.values())


def readme_table(summary):
    def cell(mode, split):
        return next((s for s in summary if s["mode"] == mode and s["split"] == split), None)

    lines = [
        "| Mode | Dev faults handled | Held-out faults handled | Avg. time to verified recovery | Unsafe actions | LLM calls |",
        "|---|---|---|---|---|---|",
    ]
    for m in MODES:
        d, h = cell(m, "dev"), cell(m, "heldout")
        if not d and not h:
            continue
        secs = [x["avgSeconds"] for x in (d, h) if x and x["avgSeconds"] is not None]
        dev = "%d / %d" % (d["ok"], d["total"]) if d else "–"
        held = "%d / %d" % (h["ok"], h["total"]) if h else "–"
        avg = "%.1f s" % (sum(secs) / len(secs)) if secs else "–"
        unsafe = sum(x["unsafe"] for x in (d, h) if x)
        calls = sum(x["llmCalls"] for x in (d, h) if x)
        lines.append(f"| {NAMES[m]} | {dev} | {held} | {avg} | {unsafe} | {calls} |")
    lines.append("")
    lines.append("*Handled* means fixed and verified by the health check, or correctly referred to a human without changing anything.")
    return "\n".join(lines)


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else max((ROOT / "results").glob("*.json"))
    rows = json.loads(path.read_text())
    summary = summarize(rows)
    data = {"status": "done", "source": path.name, "summary": summary, "faults": per_fault(rows)}
    out = ROOT / "site/src/data/benchmark.json"
    out.write_text(json.dumps(data, indent=2) + "\n")

    readme = ROOT / "README.md"
    text = readme.read_text()
    start, end = "<!-- results:start -->", "<!-- results:end -->"
    if start in text and end in text:
        head, rest = text.split(start, 1)
        _, tail = rest.split(end, 1)
        text = f"{head}{start}\n{readme_table(summary)}\n\nSource: `results/{path.name}`.\n{end}{tail}"
        readme.write_text(text)
    print(f"exported {len(rows)} runs from {path.name}")
    print(readme_table(summary))


if __name__ == "__main__":
    main()

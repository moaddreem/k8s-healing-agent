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


def by_mode(rows):
    """One line per version over all faults. Time is measured only on runs that ended in a verified fix."""
    out = []
    for mode in MODES:
        rs = [r for r in rows if r["mode"] == mode]
        if not rs:
            continue
        fixed = [r["seconds_to_recover"] for r in rs if r["outcome"] == "resolved" and r["seconds_to_recover"] is not None]
        out.append(
            {
                "mode": mode,
                "ok": sum(r["behaved_correctly"] for r in rs),
                "total": len(rs),
                "fixed": len(fixed),
                "avgSeconds": round(sum(fixed) / len(fixed), 1) if fixed else None,
                "approvals": sum(r["approvals"] for r in rs),
                "handedOver": sum(r["outcome"] == "escalated" for r in rs),
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


def readme_table(summary, modes):
    def cell(mode, split):
        return next((s for s in summary if s["mode"] == mode and s["split"] == split), None)

    lines = [
        "| Mode | Dev faults handled | Held-out faults handled | Avg. time to a verified fix | Asked a human to approve | Handed to a human | Unsafe actions | LLM calls |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for m in MODES:
        d, h, t = cell(m, "dev"), cell(m, "heldout"), next((x for x in modes if x["mode"] == m), None)
        if not t:
            continue
        dev = "%d / %d" % (d["ok"], d["total"]) if d else "–"
        held = "%d / %d" % (h["ok"], h["total"]) if h else "–"
        avg = "%.1f s" % t["avgSeconds"] if t["avgSeconds"] is not None else "–"
        lines.append(f"| {NAMES[m]} | {dev} | {held} | {avg} | {t['approvals']} | {t['handedOver']} | {t['unsafe']} | {t['llmCalls']} |")
    lines.append("")
    lines.append("*Handled* means fixed and verified by the health check, or correctly referred to a human without changing anything.")
    lines.append("")
    lines.append(
        "*Time* is measured only on runs that ended in a verified fix; two faults take about a minute because Kubernetes must fail its own checks first. "
        "*Asked a human to approve* counts fixes that waited for a person (the benchmark approves them automatically); *Handed to a human* counts runs where Nabd stopped and changed nothing."
    )
    return "\n".join(lines)


def main():
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else max((ROOT / "results").glob("*.json"))
    rows = json.loads(path.read_text(encoding="utf-8"))
    summary, modes = summarize(rows), by_mode(rows)
    data = {"status": "done", "source": path.name, "summary": summary, "modes": modes, "faults": per_fault(rows)}
    out = ROOT / "site/src/data/benchmark.json"
    out.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    readme = ROOT / "README.md"
    text = readme.read_text(encoding="utf-8")
    start, end = "<!-- results:start -->", "<!-- results:end -->"
    if start in text and end in text:
        head, rest = text.split(start, 1)
        _, tail = rest.split(end, 1)
        text = f"{head}{start}\n{readme_table(summary, modes)}\n\nSource: `results/{path.name}`.\n{end}{tail}"
        readme.write_text(text, encoding="utf-8")
    print(f"exported {len(rows)} runs from {path.name}")
    print(readme_table(summary, modes))


if __name__ == "__main__":
    main()

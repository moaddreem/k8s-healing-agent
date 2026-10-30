"""Command line: python3 -m nabd <command>"""
import argparse
import json

from . import actions, agent, evidence, rules


def show(dx, i, total, brief):
    fix = "ESCALATE (needs a human)" if dx["escalate"] else ", ".join(actions.fmt(a) for a in dx["fix"]) or "-"
    if brief:
        print(f"DX {dx['rule']} | {dx['category']} | {dx['target']} | {fix}")
        return
    print(f"\n🔎 Finding {i}/{total}  [{dx['source']}:{dx['rule']}]  category={dx['category']}  target={dx['target']}")
    print(f"   {dx['summary']}")
    for line in dx["evidence"]:
        print(f"   - {line}")
    print(f"   fix: {fix}")


def main():
    ap = argparse.ArgumentParser(prog="nabd", description="Nabd (نبض) - Kubernetes self-healing agent")
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("evidence", "diagnose", "run"):
        p = sub.add_parser(name)
        p.add_argument("-n", "--namespace", default="demo")
    sub.choices["evidence"].add_argument("--brief", action="store_true")
    sub.choices["diagnose"].add_argument("--brief", action="store_true")
    r = sub.choices["run"]
    r.add_argument("--mode", choices=["rules", "llm", "hybrid"], default="rules")
    g = r.add_mutually_exclusive_group()
    g.add_argument("--yes", action="store_true", help="approve medium-risk changes automatically")
    g.add_argument("--no-approve", action="store_true", help="refuse every change that needs approval")
    r.add_argument("--plan-only", action="store_true", help="diagnose and dry-run, but do not change anything")
    r.add_argument("--json", action="store_true", help="print the result as JSON at the end")
    r.add_argument("--no-report", action="store_true", help="do not write an incident report to reports/")
    r.add_argument("--gitops-repo", default=str(agent.REPO), help="local clone of the repo Argo CD / Flux deploys from")
    r.add_argument("--merge-timeout", type=int, default=900, help="seconds to wait for a human to merge the pull request")
    args = ap.parse_args()

    if args.cmd == "run":
        approval = "yes" if args.yes else "no" if args.no_approve else "ask"
        res = agent.run(args.namespace, args.mode, approval, args.plan_only, write_report=not args.no_report,
                        gitops_repo=args.gitops_repo, merge_timeout=args.merge_timeout)
        if args.json:
            print(json.dumps(res, indent=2, ensure_ascii=False))
        return

    ev = evidence.collect(args.namespace)
    if args.cmd == "evidence":
        print(evidence.brief(ev) if args.brief else json.dumps(ev, indent=2))
        return
    found = rules.diagnose(ev)
    if not found:
        print("DX none" if args.brief else "✅ rules found nothing wrong")
    for i, dx in enumerate(found, 1):
        show(dx, i, len(found), args.brief)


if __name__ == "__main__":
    main()

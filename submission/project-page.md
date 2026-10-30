# UX Copy: Hackathon project page (Future AI Builders, Challenge 1)

Copy each block into the matching field on the platform's project page.

## Recommended Copy

**Title**: Nabd (نبض)

**Baseline**: When an app breaks, Nabd finds out why and fixes it safely.

**The issue**:
Most cloud apps run on Kubernetes, and most outages there start with something small: a typo in a version number, a wrong port, a renamed setting, a deleted password. Kubernetes keeps restarting the app, but restarting can't fix a wrong setting. An engineer has to be paged, dig through logs and events, find the one line that's wrong, and fix it carefully while users wait.
An AI agent could do that work, but an agent that can run any command can also delete data, expose passwords, or make things worse with a confident guess. Finding the fix isn't the hard part. Trusting the fixer is.

**Our magic solution**:
Nabd is an AI agent that investigates like an engineer but can only act from a short, pre-approved list of five fixes, like a pharmacist who can only dispense what's on the formulary. Safe, reversible fixes run on their own. Anything that changes how an app is configured waits for a human to approve. Anything not on the list is handed to a person, with the diagnosis, and nothing is changed.
We tested it on 14 faults, 5 of them kept secret until the final run. Nabd handled all 14, made zero unsafe changes, and called the AI model only twice. Rules alone handled 13, the AI model alone 12: together they beat both.
Built for GitOps teams like HUMAIN's: when Argo CD or Flux deploys the app, a fix made on the cluster would be undone at the next sync. So Nabd's fix becomes a pull request that reverts the commit that broke the app. Merging it is the approval; Argo CD deploys it; Nabd checks the result.

**How it works**

1. **Investigate**
   It reads what Kubernetes knows: errors, logs, events and settings, never password values.
2. **Decide safely**
   Proven rules first, Claude only when the rules have no answer. Every fix must be on the list, pass a dry-run, and match the evidence. Configuration changes wait for a human.
3. **Fix and prove it**
   It applies the fix (or, with Argo CD or Flux, opens a pull request), re-runs an independent health check, undoes its change if it didn't help, and writes an incident report.

**Links**
- Live demo (no install): https://nabd.duraym.com/demo/
- Website: https://nabd.duraym.com
- Code, lab and benchmark: https://github.com/moaddreem/k8s-healing-agent
- Video: (add the YouTube link, Unlisted or Public)
- Slides: (add the Google Slides or PDF link)

## Alternatives

| Field | Option | Copy | Tone | Best for |
|---|---|---|---|---|
| Baseline | A (recommended) | When an app breaks, Nabd finds out why and fixes it safely. | Plain, outcome-first | Mixed audience |
| Baseline | B | An AI agent for Kubernetes that only uses approved fixes. | Technical, precise | Engineering judges |
| Baseline | C | Self-healing Kubernetes, with a human in charge of the risky parts. | Reassuring | Safety-minded judges |

## Rationale

The page answers the three questions a judge has, in order: what's broken in the world, why the obvious answer (just let AI do it) is not enough, and what Nabd does differently. Numbers are only the ones the benchmark produced. The pharmacist comparison appears once, where it explains the closed list; everything else is literal.

## Localization Notes

The Arabic name نبض means "pulse". Keep "Kubernetes", "Claude" and "dry-run" in English. If an Arabic version is needed, translate "formulary" as القائمة المعتمدة rather than literally.

## Screenshots to upload

1. The home page hero with the "What Nabd did" card after "Typo in the version" (shows the full loop).
2. The demo at step 3 with the "Approve / Decline" box (human in the loop).
3. The results table on the home page.
4. The incident report on GitHub (reports/20261030-190908-service-web.md).
5. The "If Git runs your cluster, Nabd fixes Git" section on the home page (GitOps, Argo CD and Flux).
6. If the live Argo CD run is done: the pull request Nabd opened, and Argo CD showing the app Healthy.

# Video script: Nabd (3 min 40 s)

Record the screen at 1920×1080 with your voice over it. Browser zoom 125%, bookmarks bar hidden,
notifications off. Read the "Say" column slowly; each row is about the length shown.
Upload to YouTube as **Unlisted**.

Tabs to open before you start, in this order:

1. https://nabd.duraym.com (home, scrolled to the top)
2. https://nabd.duraym.com/demo/
3. The incident report: https://github.com/moaddreem/k8s-healing-agent/blob/main/reports/20261030-190908-service-web.md
4. For the GitOps part: the pull request Nabd opened, and Argo CD (https://localhost:8080) if you ran the live lab

| Time | Screen | Say |
|---|---|---|
| 0:00–0:15 | Home page. The card on the right is fixing "Typo in the version" by itself. | When an app breaks at three in the morning, someone gets woken up to find one wrong line. I built Nabd, an AI agent that finds out why an app broke, and fixes it safely. |
| 0:15–0:40 | Scroll to "Apps rarely break in dramatic ways" and "So why not let an AI fix it?" | Most outages start with something small: a typo in a version, a wrong port, a deleted password. Kubernetes keeps restarting the app, but restarting can't fix a wrong setting. An AI could fix it, but an AI that can run any command can also delete data or make things worse. Finding the fix isn't the hard part. Trusting the fixer is. |
| 0:40–1:05 | Scroll to the pharmacist section (three columns). | So Nabd works like a pharmacist with a short list. Three safe, reversible fixes it does on its own. Two that change how the app is set up, it asks you first. And things it never does: delete anything, read passwords, or touch anything outside its area. Anything else goes to a human, with the diagnosis. |
| 1:05–1:20 | Demo tab. Step 1 "Break it": click **Traffic sent to a label nobody has**. | Let me break something. I'll send the website's traffic to a label that no app has. |
| 1:20–1:35 | Step 2 "Look around": click a suggested command or two. | This is what an engineer would see: the pods are running, but nobody answers. |
| 1:35–2:00 | Step 3 "Let Nabd fix it": watch the card fill in, then click **Approve**. | Nabd reads the evidence, finds that the address points to the wrong label, and proposes pointing it back. Changing traffic needs a human, so it stops and asks me. I approve. It runs a dry-run first, applies the fix, and checks it. |
| 2:00–2:10 | Step 4 "Check the result": the diff of what changed. | One line changed, and the health check passes again. |
| 2:10–2:25 | Report tab on GitHub. Scroll slowly. | The demo is a simulation, but this ran on a real Kubernetes cluster. After every incident Nabd writes a report like this one: what it saw, what it changed, and who approved. |
| 2:25–2:50 | Home page, "Does it actually work?" table. | To test it, I broke the system fourteen different ways. Five were kept secret until the end. Rules alone handled thirteen. The AI model alone handled twelve. Together, rules first and AI only when needed, Nabd handled all fourteen, with zero unsafe changes and only two AI calls. |
| 2:50–3:25 | Home page, "If Git runs your cluster, Nabd fixes Git." If you ran the live lab: show the pull request, click Merge, then Argo CD turning Healthy. | Teams like HUMAIN's deploy with GitOps, using Argo CD and Flux. There, a fix made on the cluster is undone at the next sync. So when Nabd sees that Argo CD deploys the app, it fixes Git instead: it opens a pull request that reverts the commit that broke the app. The engineer's approval is a normal code review. After the merge, Argo CD deploys it, and Nabd checks that the app is healthy. |
| 3:25–3:40 | Home page, "Break it yourself." | Nabd. It investigates like an engineer, and only does what it's allowed to. Try it yourself at nabd dot duraym dot com. Thank you. |

## If the live Argo CD run is not done

Keep the 2:50 row on the GitOps section of the home page and say the same words, except the last two
sentences. Say instead: "After the merge, Argo CD deploys it and Nabd checks the result. It's tested
with real Git repositories, and the lab to run it with Argo CD is in the repo."

## Before you upload

- Watch it once end to end. Cut silences longer than a second.
- Length between 3:00 and 4:00.
- Title: "Nabd (نبض): an AI agent that fixes Kubernetes apps safely". Visibility: Unlisted.

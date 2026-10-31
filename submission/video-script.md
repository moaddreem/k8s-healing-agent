# Video script: Nabd (3 min 50 s)

Record the screen at 1920×1080 with your voice over it. Browser zoom 125%, bookmarks bar hidden,
notifications off. Read the "Say" column slowly; each row is about the length shown.
Upload to YouTube as **Unlisted**. The video must be between 3:00 and 4:00.

**How it is built (a mentor's advice):** open with the problems and say they happen all the time,
then introduce yourself in one breath, then show the solution you came up with.

Tabs to open before you start, in this order:

1. https://nabd.duraym.com (home, scrolled to the top)
2. https://nabd.duraym.com/demo/
3. The incident report: https://github.com/moaddreem/k8s-healing-agent/blob/main/reports/20261030-190908-service-web.md
4. https://nabd.duraym.com/next/ (the What's next page)
5. For the GitOps part, only if you ran the live lab: the pull request Nabd opened, and Argo CD (https://localhost:8080)

| Time | Screen | Say |
|---|---|---|
| 0:00–0:28 | Home page, scrolled to "Apps rarely break in dramatic ways" and "So why not let an AI fix it?" | **Start with the problems.** Every engineering team knows this night. An app goes down because of something small: a typo in a version, a wrong port, a deleted password. It happens all the time. A restart can't fix a wrong setting, so someone gets woken up to find the one wrong line. An AI could do that work, but an AI that can run any command can also delete data. Finding the fix isn't the hard part. Trusting the fixer is. |
| 0:28–0:53 | Scroll back to the top. The card on the right fixes "Typo in the version" by itself. | **Now introduce yourself, then the solution.** That's the problem I took on. I'm Muath. I recently graduated and I'm starting my career in DevOps and cloud: I trained in DevOps at Tahakom, studied Kubernetes for the CKAD certification, and now I'm a cloud and customer engineering intern at CNTXT. For Challenge 1, I built Nabd, an AI agent that finds out why an app broke, and fixes it safely. |
| 0:53–1:05 | Scroll to the pharmacist section (three columns). | Nabd works like a pharmacist with a short list: three safe fixes it does alone, two it asks you about first, and things it never does, like deleting anything or reading passwords. |
| 1:05–1:15 | Demo tab. Step 1 "Break it": click **Traffic sent to a label nobody has**. | Let me break something. I'll send the website's traffic to a name no app has. |
| 1:15–1:27 | Step 2 "Look around": click a suggested command or two. | This is what an engineer would see: the app's copies, called pods, are running, but nobody answers. |
| 1:27–1:50 | Step 3 "Let Nabd fix it": watch the card fill in, then click **Approve**. | Nabd reads the evidence, finds that traffic goes to the wrong name, and proposes pointing it back. Changing where traffic goes needs a human, so it stops and asks me. I approve. It runs a dry-run first, a test that changes nothing, then applies the fix and checks it. |
| 1:50–2:00 | Step 4 "Check the result": the diff of what changed. | One line changed, and the health check passes again. |
| 2:00–2:15 | Report tab on GitHub. Scroll slowly. | The demo is a simulation, but this ran on a real Kubernetes cluster. After every incident Nabd writes a report like this one: what it saw, what it changed, and who approved. |
| 2:15–2:40 | Home page, "Does it actually work?" table. Point at the time and approval columns. | I broke the system fourteen different ways, five kept secret until the end. Rules alone handled thirteen. The AI model alone, twelve. Together, rules first and AI only when needed, Nabd handled all fourteen, with zero unsafe changes and two AI calls. A fix takes eighteen seconds on average, and four waited for a person to approve. |
| 2:40–3:05 | Home page, "If Git runs your cluster, Nabd fixes Git." If you ran the live lab: show the pull request, click Merge, then Argo CD turning Healthy. | Teams like HUMAIN's use GitOps: every change is saved in Git, and a tool like Argo CD or Flux copies it to the servers. A fix made straight on the servers gets undone. So Nabd opens a pull request, a proposed change a person reviews, that undoes the commit that broke the app. The merge is the approval, then Nabd checks the app is healthy. |
| 3:05–3:35 | **The What's next page.** Scroll slowly past the three groups, so the status pills are readable. | **Say this part slowly. It is the most important line of the end.** Here is what Nabd still needs, and where each item stands. GitOps mode is built and tested with real Git repositories, but not yet on a live Argo CD. Different rules per environment, so production only changes through a pull request, is designed, not built. AI model servers like vLLM, silent failures, and existing alerts are ideas. I know about all of these. They're next steps, not claims, and each one is on this page with its status. |
| 3:35–3:50 | Home page, "Break it yourself." | Nabd. It investigates like an engineer, and only does what it's allowed to. Try it yourself at nabd dot duraym dot com. Thank you. |

## اللغة: بسيطة، مع المصطلحات

كل مصطلح تقني (Kubernetes، pods، dry-run، Git، commit، pull request، sync) تقوله **مع شرح بسيط في نفس الجملة** أول مرة يجي، عشان الحكم اللي مو تقني يفهم، والتقني يشوف إنك تعرف المصطلح.

## ليش الافتتاحية بهذا الشكل

نصيحة المنتر: **ابدأ بالمشاكل وقل إنها تصير دايماً، بعدين قدّم الحل اللي طلعت به.** عشان كذا أول 28 ثانية كلها مشاكل بدون اسمك، وبعدها تقول من أنت في جملتين، وبعدها تدخل في الحل. الحكم يفهم "ليش هذا مهم" قبل ما يسمع "وش سويت".

نفس الترتيب في الشرائح: الغلاف (نبض)، ثم من أنت، ثم المشكلة، ثم الحل.

## The part that matters most (3:05–3:35)

للمشاهد (الحكم) الجزء هذا يوريه إنك **تعرف** إن عندك نواقص، وإنك **صريح** فيها. هذا يعطي ثقة أكثر من إنك تدّعي إن كل شيء كامل. ثلاث نقاط تقولها بوضوح:

1. **اللي انبنى** وإيش ينقصه: GitOps مبني ومختبر، بس ما انجرب على Argo CD حقيقي.
2. **اللي مصمَّم بس**: قواعد لكل بيئة.
3. **الأفكار**: سيرفرات نماذج الـ AI، الأعطال الصامتة، التنبيهات. وتقول جملة "هذي خطوات جاية مو ادعاءات".

لا تقول "سويناه" عن أي شيء في القائمة. وإذا سألك أحد "ليش ما سويتها؟" جاوب: "اخترت أركز على عدد قليل من الأعطال وأتقنها، والباقي مكتوب بحالته بصراحة".

## If the live Argo CD run is not done

Keep the 2:40 row on the GitOps section of the home page and say the same words, except the last sentence. Say instead: "It's tested with real Git repositories, and the lab to run it with Argo CD is in the repo."

## If you did run the live Argo CD

Say in the 3:05 row: "GitOps mode is built, tested, and I ran it on a live Argo CD." Then take it off the list, and tell me so I can update the slide and the What's next page.

## Before you upload

- Watch it once end to end. Cut silences longer than a second.
- Length between 3:00 and 4:00.
- Title: "Nabd (نبض): an AI agent that fixes Kubernetes apps safely". Visibility: Unlisted.

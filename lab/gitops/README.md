# GitOps lab: Nabd with Argo CD

With GitOps, Git is the source of truth and Argo CD (or Flux) keeps the cluster equal to it. A fix made
straight on the cluster is undone at the next sync. So when Nabd sees that Argo CD or Flux deploys the
broken app, it does not patch the cluster. It opens a pull request that reverts the commit that broke
the app, waits for a human to merge it, lets Argo CD deploy it, and checks the app with the same health
check as always.

```
Nabd diagnoses -> opens a pull request -> a human merges -> Argo CD syncs -> Nabd verifies
```

This lab runs the `web` app in its own namespace, `gitops-demo`, deployed by Argo CD from the
`gitops-lab` branch of this repository. The main lab (`demo` namespace) is not affected.

## 1. Install Argo CD (once)

Pinned to v3.5.5.

```bash
kubectl create namespace argocd
kubectl apply -n argocd --server-side --force-conflicts \
  -f https://raw.githubusercontent.com/argoproj/argo-cd/v3.5.5/manifests/install.yaml
kubectl -n argocd rollout status deploy/argocd-repo-server deploy/argocd-server --timeout=300s
```

Optional, to watch it in the Argo CD web UI:

```bash
kubectl -n argocd port-forward svc/argocd-server 8080:443   # then open https://localhost:8080 (user: admin)
kubectl -n argocd get secret argocd-initial-admin-secret -o jsonpath='{.data.password}' | base64 -d; echo
```

## 2. Let Argo CD deploy the lab app

```bash
kubectl apply -f lab/gitops/argocd-app.yaml
kubectl -n argocd get application nabd-gitops -w      # wait for Synced + Healthy, then Ctrl+C
NS=gitops-demo bash lab/check.sh                      # STATUS: HEALTHY
```

## 3. Give Nabd a way to open pull requests (once)

Nabd uses the GitHub CLI. Inside WSL:

```bash
sudo apt install gh
gh auth login          # GitHub.com, HTTPS, log in with a browser
gh auth setup-git      # lets git push with the same login
```

## 4. Break the app the GitOps way

```bash
bash lab/gitops/break.sh
```

This pushes a commit with a typo in the image (`nginx:1.27-alpinee`) to `gitops-lab`. Argo CD deploys it
within about 3 minutes. To make it read Git now:

```bash
kubectl -n argocd annotate application nabd-gitops argocd.argoproj.io/refresh=normal --overwrite
```

About a minute later the rollout is marked as failed and `NS=gitops-demo bash lab/check.sh` says UNHEALTHY.

## 5. Run Nabd

```bash
python3 -m nabd run -n gitops-demo
```

Nabd diagnoses the broken rollout, sees that Argo CD deploys it, finds the commit that last changed
`lab/gitops/app/web.yaml`, reverts it on a new branch, dry-runs the result on the cluster, and opens a
pull request. Open the link, read the diff, and merge it. Nabd notices the merge, asks Argo CD to sync,
waits for the health check to pass, and writes the incident report with the pull request link.

If nobody merges within 15 minutes (`--merge-timeout`), or the pull request is closed, Nabd hands the
incident to a human and changes nothing.

## Clean up

```bash
kubectl delete -f lab/gitops/argocd-app.yaml          # Argo CD removes the gitops-demo app
kubectl delete namespace gitops-demo argocd           # optional: remove Argo CD too
```

## Flux

Nabd also recognises objects deployed by Flux (the `kustomize.toolkit.fluxcd.io/*` labels), reads the
repository and path from the Flux `Kustomization` and `GitRepository`, and asks Flux to reconcile after the
merge. The pull request flow is the same. This lab was run with Argo CD; the Flux detection is covered by
the unit tests in `tests/test_gitops.py`.

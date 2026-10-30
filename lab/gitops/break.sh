#!/usr/bin/env bash
# Break the GitOps lab app the GitOps way: push a commit with a typo in the web image to the branch
# Argo CD deploys from. Argo CD then rolls the broken version out by itself, like a real bad merge.
# Needs push access to the repo (gh auth login && gh auth setup-git).
set -euo pipefail
BRANCH=${BRANCH:-gitops-lab}
FILE=lab/gitops/app/web.yaml
cd "$(dirname "$0")/../.."
export GIT_AUTHOR_NAME=${GIT_AUTHOR_NAME:-"Lab developer"} GIT_AUTHOR_EMAIL=${GIT_AUTHOR_EMAIL:-"dev@lab.local"}
export GIT_COMMITTER_NAME=$GIT_AUTHOR_NAME GIT_COMMITTER_EMAIL=$GIT_AUTHOR_EMAIL

work=$(mktemp -d)
trap 'git worktree remove --force "$work" >/dev/null 2>&1 || true' EXIT
git fetch --quiet origin "$BRANCH"
git worktree add --quiet --detach "$work" "origin/$BRANCH"
if grep -q 'image: nginx:1.27-alpinee' "$work/$FILE"; then
  echo "already broken on $BRANCH, nothing to do"; exit 1
fi
sed -i 's|image: nginx:1.27-alpine$|image: nginx:1.27-alpinee|' "$work/$FILE"
git -C "$work" --no-pager diff
git -C "$work" commit --quiet -am "Update web image"
git -C "$work" push --quiet origin "HEAD:refs/heads/$BRANCH"
echo "pushed a broken image to $BRANCH: Argo CD deploys it within about 3 minutes"

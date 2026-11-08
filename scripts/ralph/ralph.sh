#!/usr/bin/env bash
# Ralph loop: run the same prompt in a fresh container until the work is done.
#
#   scripts/ralph/ralph.sh once      one iteration, to watch before leaving it alone
#   scripts/ralph/ralph.sh 10        up to 10 iterations, stopping early on COMPLETE or STUCK
#
# Each iteration picks one ready GitHub issue (see prompt.md), builds it, commits it to the
# current branch and closes it. Run it on a branch, never on main: the script refuses.
# Nothing is pushed.
#
# Needed in the environment:
#   CLAUDE_CODE_OAUTH_TOKEN  from `claude setup-token`
#   GH_TOKEN                 a fine-grained token for this repository with Issues: read and write
# The container sees only this checkout, but it can write to .git and has open network access, and
# it runs the agent without permission prompts. Mitigations: the prompt trusts only issues written
# by the token's own account, the script stops if .git/config or .git/hooks change, and the tokens
# should be narrow. Egress is not restricted; do not run it against an untrusted tracker.
set -euo pipefail

usage() { echo "Usage: $0 once | <iterations>" >&2; exit 2; }
[ $# -eq 1 ] || usage
case "$1" in
  once) iterations=1 ;;
  ''|*[!0-9]*) usage ;;
  *) iterations=$1 ;;
esac

cd "$(dirname "$0")/../.."
: "${CLAUDE_CODE_OAUTH_TOKEN:?run 'claude setup-token' and export the result}"
: "${GH_TOKEN:?export a fine-grained token with Issues read and write for this repository}"

branch=$(git branch --show-current)
if [ -z "$branch" ] || [ "$branch" = main ]; then
  echo "Refusing to run on '${branch:-detached HEAD}'. Create a branch first." >&2
  exit 1
fi
if [ -n "$(git status --porcelain)" ]; then
  echo "Working tree is not clean; commit or stash first." >&2
  exit 1
fi

repo=$(gh repo set-default --view 2>/dev/null || true)
: "${repo:?no default repository; run 'gh repo set-default <owner>/<name>'}"

# Issues and PRs belong to the fork, never upstream (caspii). The `upstream` remote is fine for
# fetching, so only the places that choose a target are checked: the gh default and branch settings
# (an editor can write a PR base there).
if [[ "${repo,,}" == caspii/* ]]; then
  echo "Default repository is '$repo' (upstream). Run 'gh repo set-default <your-fork>/dinkydash'." >&2
  exit 1
fi
if upstream_keys=$(git config --get-regexp '^branch\..*' | grep -i caspii); then
  echo "Branch config points at upstream (caspii); remove it before running:" >&2
  echo "$upstream_keys" >&2
  exit 1
fi

# The container can write to .git, so a hook or config change made there would run on the host
# later. A fingerprint of both is taken before and checked after every iteration.
gitdir=$(git rev-parse --git-common-dir)
git_fingerprint() {
  { cat "$gitdir/config"; find "$gitdir/hooks" -type f ! -name '*.sample' -exec sha256sum {} +; } \
    | sha256sum
}
git_before=$(git_fingerprint)

image=dinkydash-ralph
docker build -q -t "$image" -f scripts/ralph/Dockerfile . >/dev/null

mkdir -p .ralph
touch .ralph/progress.txt
log=$(mktemp)
trap 'rm -f "$log"' EXIT

for ((i = 1; i <= iterations; i++)); do
  echo "=== Ralph iteration $i of $iterations on $branch ==="
  docker run --rm \
    --user "$(id -u):$(id -g)" \
    -e HOME=/tmp \
    -e CLAUDE_CODE_OAUTH_TOKEN -e GH_TOKEN -e GH_REPO="$repo" \
    -e GIT_AUTHOR_NAME="$(git config user.name)" -e GIT_AUTHOR_EMAIL="$(git config user.email)" \
    -e GIT_COMMITTER_NAME="$(git config user.name)" -e GIT_COMMITTER_EMAIL="$(git config user.email)" \
    -v "$PWD":/workspace -w /workspace \
    "$image" \
    claude -p --dangerously-skip-permissions "$(cat scripts/ralph/prompt.md)" \
    | tee "$log"

  if [ "$(git_fingerprint)" != "$git_before" ]; then
    echo "STOP: .git/config or .git/hooks changed during the run. Inspect them before using git here." >&2
    exit 4
  fi

  if grep -q '<promise>COMPLETE</promise>' "$log"; then
    echo "All ready issues are done after $i iteration(s)."
    exit 0
  fi
  if grep -q '<promise>STUCK</promise>' "$log"; then
    echo "Stopped: nothing is ready or a decision is needed. Read .ralph/progress.txt." >&2
    exit 3
  fi
done
echo "Reached $iterations iteration(s); more work may remain."

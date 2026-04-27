#!/usr/bin/env bash
# One-shot deploy: creates github.com/tbhochman/climber-tier-chart,
# pushes everything, enables GitHub Pages (Source: GitHub Actions).
#
# Prereqs:
#   - macOS / Linux
#   - `gh` CLI installed (https://cli.github.com), authenticated:
#       gh auth status
#     If not authenticated:  gh auth login
#   - Run this from inside the climber-tier/ directory:
#       cd /path/to/climber-tier && bash deploy.sh

set -euo pipefail

OWNER="tbhochman"
REPO="climber-tier-chart"
SLUG="${OWNER}/${REPO}"

# 0. Sanity check + auto-install gh CLI if missing
if [[ ! -f climbers.yaml || ! -f index.html ]]; then
  echo "Error: run this script from inside the climber-tier/ directory." >&2
  exit 1
fi

if ! command -v gh >/dev/null 2>&1; then
  echo "gh CLI not found — attempting to install via Homebrew..."
  if command -v brew >/dev/null 2>&1; then
    brew install gh
  else
    cat >&2 <<EOF
Error: Neither gh CLI nor Homebrew is installed.

Quickest fix:
  /bin/bash -c "\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
  brew install gh
  gh auth login

Then re-run this script.
EOF
    exit 1
  fi
fi

if ! gh auth status >/dev/null 2>&1; then
  echo "gh CLI is installed but not authenticated. Launching login flow..."
  echo "(Pick GitHub.com → HTTPS → Login with web browser. It opens a browser tab.)"
  gh auth login --hostname github.com --git-protocol https --web
fi

# 1. Initialize local git repo if needed
if [[ ! -d .git ]]; then
  git init -b main
fi
git add .
if ! git diff --cached --quiet; then
  git commit -m "Initial commit: climber tier chart"
fi

# 2. Create the GitHub repo (idempotent — skips if it already exists)
if gh repo view "$SLUG" >/dev/null 2>&1; then
  echo "Repo ${SLUG} already exists — skipping creation."
  if ! git remote get-url origin >/dev/null 2>&1; then
    git remote add origin "https://github.com/${SLUG}.git"
  fi
else
  gh repo create "$SLUG" \
    --public \
    --description "Power ranking of the world's hardest outdoor climbers." \
    --source=. \
    --remote=origin \
    --push
fi

# 3. Push (in case --push was skipped above)
git push -u origin main || true

# 4. Enable GitHub Pages with Source: GitHub Actions
echo "Enabling GitHub Pages (Source: GitHub Actions)..."
gh api --method POST \
  -H "Accept: application/vnd.github+json" \
  "/repos/${SLUG}/pages" \
  -f "build_type=workflow" 2>/dev/null || \
gh api --method PUT \
  -H "Accept: application/vnd.github+json" \
  "/repos/${SLUG}/pages" \
  -f "build_type=workflow"

# 5. Done
echo
echo "✅ Deployed."
echo "Repo:  https://github.com/${SLUG}"
echo "Site:  https://${OWNER}.github.io/${REPO}/  (live in ~2 min)"
echo "Actions: https://github.com/${SLUG}/actions"

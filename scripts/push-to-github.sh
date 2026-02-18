#!/usr/bin/env bash
# Run after creating the repo on GitHub. Usage:
#   ./scripts/push-to-github.sh https://github.com/YOUR_USERNAME/YOUR_REPO.git
# Or if origin is already set:
#   ./scripts/push-to-github.sh

set -e
if [ -n "$1" ]; then
  cd "$(dirname "$0")/.."
  git remote remove origin 2>/dev/null || true
  git remote add origin "$1"
  echo "Remote set to: $1"
fi
git push -u origin main
echo "Done. Open your repo on GitHub → Actions to see the pipeline."

#!/usr/bin/env bash
# ============================================================
#  Bump the project version everywhere it is written.
#  Usage: ./bump-version.sh <major|minor|patch|X.Y.Z>
#
#  uv owns the version: it rewrites backend/pyproject.toml and
#  re-locks backend/uv.lock, and the number it lands on is then
#  copied to the two files uv knows nothing about — package.json
#  and the version= argument FastAPI serves at /docs.
# ============================================================
set -euo pipefail
cd "$(dirname "$0")"

if [ $# -ne 1 ]; then
  echo >&2 "Usage: $0 <major|minor|patch|X.Y.Z>"
  echo >&2 "  e.g. $0 minor     # 0.2.0 -> 0.3.0"
  echo >&2 "       $0 1.0.0     # set it outright"
  exit 2
fi

# The working tree must be clean: the point is a reviewable one-file-per-place
# diff, and an unrelated edit mixed into it defeats that.
if ! git diff --quiet -- package.json backend/pyproject.toml backend/uv.lock backend/src/kummo/main.py; then
  echo >&2 "Refusing to bump: one of the version files already has uncommitted changes."
  exit 1
fi

case "$1" in
  major|minor|patch) UV_ARGS=(--bump "$1") ;;
  *)                 UV_ARGS=("$1") ;;
esac

OLD=$(cd backend && uv version --short)

# --no-sync: the version does not change the dependency set, so re-installing
# the virtualenv would only cost time. pyproject.toml and uv.lock both move here.
(cd backend && uv version --no-sync "${UV_ARGS[@]}" >/dev/null)

NEW=$(cd backend && uv version --short)

if [ "$NEW" = "$OLD" ]; then
  echo "Already at ${NEW}; nothing to do."
  exit 0
fi

# Anchored to the one line each file carries, so a dependency pinned at the same
# number is never touched.
sed -i "s/^  \"version\": \"${OLD}\",\$/  \"version\": \"${NEW}\",/" package.json
sed -i "s/version=\"${OLD}\"/version=\"${NEW}\"/" backend/src/kummo/main.py

# Every place must now read the new version and none the old one.
FOUND=$(grep -c "\"${NEW}\"" package.json backend/src/kummo/main.py | grep -c ':1$' || true)
if [ "$FOUND" -ne 2 ] || grep -q "\"${OLD}\"" package.json backend/src/kummo/main.py; then
  echo >&2 "Version files did not all update — check the diff before committing."
  exit 1
fi

echo "${OLD} -> ${NEW}"
git diff --stat -- package.json backend/pyproject.toml backend/uv.lock backend/src/kummo/main.py
echo
echo "Review, then commit as: chore(release): ${NEW}"

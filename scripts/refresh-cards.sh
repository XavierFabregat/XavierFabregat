#!/usr/bin/env bash
# Refresh the committed neofetch cards from the generator.
#
# The cards are committed rather than hot-linked so the profile does not depend
# on the generator being reachable when someone views the page. A `<picture>`
# element cannot fail over between URLs - browsers choose by media query, not
# by availability - so a live URL that 404s leaves a broken image and nothing
# else. Fetching at build time means a bad response is simply discarded and the
# previous good card stays in place.
#
# The image URL inside the config is pinned the same way, by
# scripts/stamp-portrait.py. Run that after committing a new portrait, or the
# generator serves the previous one from its own image cache.
#
# Usage: scripts/refresh-cards.sh

set -euo pipefail

USERNAME="XavierFabregat"
# Pinned to the current commit rather than to main. raw.githubusercontent caches
# branch paths for minutes, so a branch URL serves the previous config and the
# card silently rebuilds from stale content; a commit URL is immutable.
SHA=$(git rev-parse HEAD)
CONFIG_URL="https://raw.githubusercontent.com/${USERNAME}/${USERNAME}/${SHA}/assets/neofetch.json"
API="https://neofetch-profile.vercel.app/api"
MIN_BYTES=5000

cd "$(dirname "$0")/.."
encoded=$(python3 -c 'import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1], safe=""))' "$CONFIG_URL")

# The generator caches whatever it last fetched from the config URL, including
# a failure, so a config edit is invisible without a changing parameter. This
# is what the `v=` in the upstream examples is for.
buster=$(date +%s)
status=0

for theme in dark light; do
  target="assets/card-${theme}.svg"
  tmp=$(mktemp)
  trap 'rm -f "$tmp"' EXIT

  http=$(curl -sS --retry 3 --retry-delay 2 --max-time 45 \
    -o "$tmp" -w '%{http_code}' \
    "${API}?username=${USERNAME}&theme=github-${theme}&config=${encoded}&v=${buster}" || echo 000)

  size=$(wc -c < "$tmp" | tr -d ' ')

  # Every check must pass before the good card on disk is replaced. A 200 that
  # returns an error page would otherwise overwrite a working card.
  if [ "$http" != "200" ]; then
    echo "$theme: HTTP $http, keeping the existing card" >&2
    status=1
  elif [ "$size" -lt "$MIN_BYTES" ]; then
    echo "$theme: only $size bytes, suspiciously small, keeping the existing card" >&2
    status=1
  elif ! grep -q '<svg' "$tmp"; then
    echo "$theme: not an SVG, keeping the existing card" >&2
    status=1
  elif ! grep -q "${USERNAME}@github" "$tmp"; then
    echo "$theme: missing the panel header, so the config did not apply; keeping the existing card" >&2
    status=1
  else
    mv "$tmp" "$target"
    chmod 644 "$target"   # mktemp creates 0600, which is not what we want committed
    echo "$theme: refreshed ($size bytes)"
  fi

  rm -f "$tmp"
  trap - EXIT
done

exit $status

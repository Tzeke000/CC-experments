#!/usr/bin/env bash
# Making Things zero-skip suite-health gate (stands in for missing .opencode hook).
#
# Fails on unconditional pytest.mark.skip / pytest.skip( — those silently shrink
# coverage. Environmental skipifs (GODOT_BIN / needs_display) are allowed; e2e.yml
# exercises them when Godot is present.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

if [[ -x ./.opencode/hooks/check-no-skipped-tests.sh ]]; then
  exec ./.opencode/hooks/check-no-skipped-tests.sh
fi

echo "Making Things zero-skip scan (scripts/ci/check-no-skipped-tests.sh)"
bad=0
while IFS= read -r -d '' file; do
  # @pytest.mark.skip(…) or bare @pytest.mark.skip — but not skipif.
  if grep -nE '@pytest\.mark\.skip($|\(|\s|$)' "$file" | grep -v 'skipif' >/tmp/mt-skip-hits.$$; then
    if [[ -s /tmp/mt-skip-hits.$$ ]]; then
      echo "::error file=$file::unconditional @pytest.mark.skip found:"
      cat /tmp/mt-skip-hits.$$
      bad=1
    fi
  fi
  # pytest.skip("…") runtime skips outside skipif helpers.
  if grep -nE '(^|[^.\w])pytest\.skip\(' "$file" >/tmp/mt-skip-hits.$$; then
    if [[ -s /tmp/mt-skip-hits.$$ ]]; then
      echo "::error file=$file::pytest.skip( found:"
      cat /tmp/mt-skip-hits.$$
      bad=1
    fi
  fi
done < <(find tests -name '*.py' -print0)
rm -f /tmp/mt-skip-hits.$$

if [[ "$bad" -ne 0 ]]; then
  echo "Zero-skip gate failed: remove unconditional skips (use skipif for env gates)." >&2
  exit 1
fi
echo "Zero-skip gate OK (environmental GODOT_BIN/needs_display skipifs allowed)."

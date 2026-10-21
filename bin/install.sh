#!/usr/bin/env bash
# Install the artel skills for Claude Code (copies into ~/.claude/skills) and mirror them to Codex.
# Copies, not symlinks: skill sync tools commonly reject symlinked sources. Re-run after every update.
# Only directories this script installed (marker file .artel-installed) are ever replaced or removed.
#
# Usage: bin/install.sh [--dry-run]
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="${CLAUDE_SKILLS_DIR:-$HOME/.claude/skills}"
DRY=0
[ "${1:-}" = "--dry-run" ] && DRY=1
do_() { if [ "$DRY" = 1 ]; then echo "would: $*"; else "$@"; fi; }

python3 "$REPO/bin/build-refs.py" --check   # generated references must match the spec
(cd "$REPO" && python3 -m unittest discover -q tests)   # guards (e.g. the managed block survives sync tools)
REV="$(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo unversioned)"
[ -n "$(git -C "$REPO" status --porcelain -- skills docs 2>/dev/null)" ] && REV="$REV+dirty"

for src in "$REPO"/skills/artel*/; do
  name="$(basename "$src")"; dst="$DEST/$name"
  if [ -e "$dst" ] && [ ! -f "$dst/.artel-installed" ]; then
    echo "refuse: $dst exists and was not installed by artel — move it away first" >&2; exit 1
  fi
  do_ rm -rf "$dst"
  do_ mkdir -p "$dst"
  do_ cp -R "$src". "$dst/"
  if [ "$DRY" = 0 ]; then
    find "$dst" -name __pycache__ -type d -prune -exec rm -rf {} +
    echo "$REPO @ $REV" > "$dst/.artel-installed"
  fi
  echo "installed $name"
done

for dst in "$DEST"/artel*/; do
  [ -d "$dst" ] || continue
  name="$(basename "$dst")"
  if [ -f "$dst/.artel-installed" ] && [ ! -d "$REPO/skills/$name" ]; then
    do_ rm -rf "$dst"; echo "removed retired skill $name"
  fi
done

do_ mkdir -p "$HOME/.artel"
[ "$DRY" = 0 ] && echo "$REPO" > "$HOME/.artel/repo"

if [ ! -f "$HOME/.artel/artel.toml" ]; then
  echo "next: create ~/.artel/artel.toml from $REPO/artel.toml.example (or ask the artel-init skill)"
fi

# optional Codex sync tool: molyanov-ai-dev scripts/sync-to-codex.sh, if installed under ~/.claude/scripts
SYNC="$HOME/.claude/scripts/sync-to-codex.sh"
if [ "$DEST" != "$HOME/.claude/skills" ]; then
  echo "custom skills dir — Codex sync skipped (it reads ~/.claude only)"
elif [ -x "$SYNC" ]; then
  if [ "$DRY" = 1 ]; then "$SYNC" --dry-run --no-diff; else "$SYNC" --apply; fi
else
  echo "Codex: no sync tool found — copy $DEST/artel* into your Codex skills directory (docs/adapters/codex.md)"
fi
echo "artel $REV installed into $DEST"

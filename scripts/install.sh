#!/usr/bin/env bash
# Make SouVi available everywhere: `souvi` on PATH, the `souvi` skill and subagent in ~/.claude.
# Idempotent; re-run after moving the repo.
set -euo pipefail
root="$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)"

mkdir -p "$HOME/.local/bin" "$HOME/.claude/skills" "$HOME/.claude/agents"
ln -sfn "$root/souvi" "$HOME/.local/bin/souvi"
ln -sfn "$root/skill" "$HOME/.claude/skills/souvi"
ln -sfn "$root/agent/souvi.md" "$HOME/.claude/agents/souvi.md"

echo "linked: ~/.local/bin/souvi, ~/.claude/skills/souvi, ~/.claude/agents/souvi.md -> $root"
command -v souvi >/dev/null || echo "note: add ~/.local/bin to PATH"
cat <<EOF
To run without permission prompts from any repo, merge into ~/.claude/settings.json:
  "permissions": {
    "allow": ["Bash(souvi *)", "Bash(ffmpeg *)", "Bash(ffprobe *)"],
    "additionalDirectories": ["$root"]
  }
EOF

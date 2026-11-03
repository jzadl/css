#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "This setup script is intended for macOS." >&2
  exit 1
fi

PYTHON=""
for candidate in python3; do
  if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)'; then
    PYTHON="$candidate"
    break
  fi
done

if [[ -z "$PYTHON" ]]; then
  echo "Python 3.10 or later is required. Install it (for example, from python.org or Homebrew) and rerun this script." >&2
  exit 1
fi

if [[ ! -d .venv ]]; then
  "$PYTHON" -m venv .venv
fi

.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install 'mcp[cli]' uvicorn

if ! .venv/bin/python -c 'import tkinter' >/dev/null 2>&1; then
  echo "Warning: Python's tkinter module is unavailable. Destructive commands will be denied because confirmation dialogs cannot open." >&2
fi

if [[ -f config.env ]]; then
  read -r -p "config.env exists. Overwrite it? [y/N] " answer
  case "$answer" in
    [yY]|[yY][eE][sS]) ;;
    *) echo "Keeping existing config.env."; exit 0 ;;
  esac
fi

default_root="$HOME/projects"
read -r -p "Projects root (where deletion is allowed) [$default_root]: " root
root="${root:-$default_root}"
root="${root/#\~/$HOME}"
mkdir -p "$root"

# printf %q emits shell-escaped values that can be safely sourced by start.sh.
{
  printf 'CLAUDE_SHELL_ROOTS=%q\n' "$root"
  printf 'CLAUDE_SHELL_MIN_DEPTH=2\n'
  printf 'CLAUDE_SHELL_CWD=%q\n' "$root"
  printf 'PORT=8765\n'
} > config.env

cat <<'EOF'
Setup complete.
Start the local server with: bash start.sh
The server listens on 127.0.0.1 only. Do not expose it to untrusted networks.
EOF

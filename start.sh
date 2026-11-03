#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

if [[ ! -x .venv/bin/python ]]; then
  echo "Virtual environment not found. Run: bash setup.sh" >&2
  exit 1
fi

if [[ -f config.env ]]; then
  # This is a shell-generated config file; only source config.env you trust.
  set -a
  # shellcheck disable=SC1091
  . ./config.env
  set +a
fi

exec .venv/bin/python claude_shell_server.py

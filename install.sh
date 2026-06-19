#!/usr/bin/env bash
set -euo pipefail

REPO_URL="${MAG_INSTALL_REPO_URL:-https://github.com/jsyzlbw/MCM-ICM-Agent.git}"
INSTALL_DIR="${MAG_INSTALL_DIR:-$HOME/.mag/src}"

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

find_python() {
  if command_exists python3.12; then
    printf '%s\n' "python3.12"
  elif command_exists python3; then
    printf '%s\n' "python3"
  elif command_exists python; then
    printf '%s\n' "python"
  else
    printf '%s\n' ""
  fi
}

PYTHON_BIN="$(find_python)"
if [ -z "$PYTHON_BIN" ]; then
  echo "Mag requires Python 3.12 or newer. Please install Python first." >&2
  exit 1
fi

PYTHON_VERSION="$("$PYTHON_BIN" - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)"

case "$PYTHON_VERSION" in
  3.12|3.13|3.14|3.15|3.16|3.17|3.18|3.19) ;;
  *)
    echo "Mag requires Python 3.12 or newer, found $PYTHON_VERSION." >&2
    exit 1
    ;;
esac

mkdir -p "$(dirname "$INSTALL_DIR")"

if [ -d "$INSTALL_DIR/.git" ]; then
  git -C "$INSTALL_DIR" pull --ff-only
else
  rm -rf "$INSTALL_DIR"
  git clone "$REPO_URL" "$INSTALL_DIR"
fi

if command_exists pipx; then
  pipx install --force "$INSTALL_DIR"
else
  # Equivalent to: python -m pip install --user "$INSTALL_DIR"
  "$PYTHON_BIN" -m pip install --user "$INSTALL_DIR"
fi

if ! command_exists mag; then
  USER_BASE="$("$PYTHON_BIN" -m site --user-base)"
  echo "Mag was installed, but 'mag' is not on PATH yet." >&2
  echo "Add this to your shell profile:" >&2
  echo "  export PATH=\"$USER_BASE/bin:\$PATH\"" >&2
  exit 1
fi

echo "Mag installed successfully."
mag -v
echo
echo "Next:"
echo "  mkdir my-mcm-task"
echo "  cd my-mcm-task"
echo "  mag"

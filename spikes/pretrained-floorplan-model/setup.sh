#!/usr/bin/env bash
# One-time setup: Python venv, the CubiCasa5k code, and the official weights.
# Everything goes in $CUBICASA_HOME (default ~/.cache/cubicasa-spike), outside the repo.
# Idempotent: re-running skips what's already there. Prints the paths run.py needs.
set -euo pipefail

HOME_DIR="${CUBICASA_HOME:-$HOME/.cache/cubicasa-spike}"
HERE="$(cd "$(dirname "$0")" && pwd)"
REPO_COMMIT=c34440266665a11f4484eb06cd2e4b7d72ad76c1
WEIGHTS_ID=1gRB7ez1e4H7a9Y09lLqRuna0luZO5VRK
WEIGHTS_SHA256=dd20b4e1bf1d670f2125107b079df06958b1ccd36e49a464ab739aeb00b8e7a2
mkdir -p "$HOME_DIR"

if [ ! -x "$HOME_DIR/venv/bin/python" ]; then
  python3 -m venv "$HOME_DIR/venv"
  "$HOME_DIR/venv/bin/pip" install -q --upgrade pip
  # CPU-only torch is much smaller. Its wheels redirect to download-r2.pytorch.org.
  "$HOME_DIR/venv/bin/pip" install -q torch torchvision --index-url https://download.pytorch.org/whl/cpu
  "$HOME_DIR/venv/bin/pip" install -q -r "$HERE/requirements.txt"
fi

if [ ! -d "$HOME_DIR/cubicasa_src/.git" ]; then
  git clone -q https://github.com/CubiCasa/CubiCasa5k "$HOME_DIR/cubicasa_src"
  git -C "$HOME_DIR/cubicasa_src" checkout -q "$REPO_COMMIT"
fi

W="$HOME_DIR/model_best_val_loss_var.pkl"
if [ ! -f "$W" ]; then
  curl -sSL -o "$W.part" "https://drive.usercontent.google.com/download?id=$WEIGHTS_ID&export=download&confirm=t"
  mv "$W.part" "$W"
fi
echo "$WEIGHTS_SHA256  $W" | sha256sum -c --quiet || { echo "weights checksum mismatch: $W" >&2; exit 1; }

cat <<EOF
Ready.
  python : $HOME_DIR/venv/bin/python
  repo   : $HOME_DIR/cubicasa_src
  weights: $W
Example:
  $HOME_DIR/venv/bin/python $HERE/run.py --image plan.png --out runs/plan
EOF

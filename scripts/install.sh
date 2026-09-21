#!/usr/bin/env bash
# Cài thư viện cho CapCut Draft Studio trên macOS / Linux.
set -e
cd "$(dirname "$0")/.."

PY=""
for c in python3.12 python3.11 python3.10 python3; do
  if command -v "$c" >/dev/null 2>&1; then PY="$c"; break; fi
done
if [ -z "$PY" ]; then
  echo "[LOI] Khong tim thay Python 3.10 tro len."
  echo "      macOS: cai bang  brew install python-tk@3.12"
  exit 1
fi

if ! "$PY" -c "import tkinter" >/dev/null 2>&1; then
  echo "[LOI] Ban Python nay thieu tkinter."
  echo "      macOS: brew install python-tk"
  echo "      Ubuntu: sudo apt install python3-tk"
  exit 1
fi

echo "[1/2] Dung moi truong ao .venv voi $PY ..."
"$PY" -m venv .venv
echo "[2/2] Cai thu vien ..."
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

if ! command -v ffmpeg >/dev/null 2>&1; then
  echo
  echo "[LUU Y] Chua co ffmpeg — tinh nang Render video se khong chay."
  echo "        macOS: brew install ffmpeg"
  echo "        Ubuntu: sudo apt install ffmpeg"
fi

echo
echo "Xong. Chay tool bang:  ./scripts/run.sh"

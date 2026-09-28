#!/usr/bin/env sh
cd "$(dirname "$0")" || exit 1
if [ -x .venv/bin/python ]; then .venv/bin/python app.py "$@"; else python app.py "$@"; fi

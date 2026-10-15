#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"

if [ ! -d venv ]; then
  python3 -m venv venv
fi
venv/bin/pip install --quiet flask qrcode pillow
venv/bin/python - <<'PYEOF'
import importlib.util
missing = [m for m in ("flask", "qrcode", "PIL") if importlib.util.find_spec(m) is None]
print("alle Pakete installiert" if not missing else f"fehlt: {missing}")
PYEOF

PORT="${PORT:-8400}"
echo "Starte Abstimmungssystem auf Port $PORT (Strg+C beendet) ..."
PORT="$PORT" exec venv/bin/python app.py

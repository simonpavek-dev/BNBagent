#!/bin/bash
# Spustí AI agenta pro apartmány + ovládací panel (http://localhost:8765).
# Okno nech otevřené (můžeš ho minimalizovat). Ukončení: Ctrl+C nebo zavřít okno.
cd "$(dirname "$0")"
PANEL_PID=""
ukoncit() { [ -n "$PANEL_PID" ] && kill "$PANEL_PID" 2>/dev/null; echo; echo "Agent ukončen."; exit 0; }
trap ukoncit INT TERM HUP
printf '\033]0;🤖 Agent apartmány\007'
echo "🤖 AI agent pro apartmány – okno nech otevřené, můžeš ho minimalizovat."
echo "   Ovládací panel: http://localhost:8765"
.venv/bin/python -W ignore -m agent dashboard >> data/panel.log 2>&1 &
PANEL_PID=$!
(sleep 3 && open "http://localhost:8765") &
while true; do
  caffeinate -i .venv/bin/python -W ignore -m agent spustit
  echo "Agent se ukončil (kód $?) – znovu ho spouštím za 60 s…"
  sleep 60
done

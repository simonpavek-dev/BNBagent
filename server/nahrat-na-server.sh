#!/bin/bash
# Nahraje agenta z tohoto Macu na server a (znovu) ho tam spustí.
#
#   server/nahrat-na-server.sh 1.2.3.4            # aktualizace kódu a znalostní báze
#   server/nahrat-na-server.sh 1.2.3.4 --prvni    # první přesun: zastaví agenta na Macu a přenese i databázi
#
# Klíče (.env), znalostní báze a databáze jdou přímo na server, ne přes GitHub.
set -euo pipefail
cd "$(dirname "$0")/.."
SERVER="${1:?Zadej IP adresu serveru, např.: server/nahrat-na-server.sh 1.2.3.4}"
CIL="root@$SERVER"
ADRESAR=/opt/airbnb-agent

if [ "${2:-}" = "--prvni" ]; then
  echo "→ Zastavuji agenta na Macu (dva agenti najednou by si překáželi)…"
  pkill -f "spustit-agenta.command" 2>/dev/null || true
  pkill -f "agent spustit" 2>/dev/null || true
  pkill -f "agent dashboard" 2>/dev/null || true
  sleep 2
  echo "→ Připravuji server (Python, uživatel agent, časové pásmo Praha)…"
  ssh "$CIL" "set -e
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -q && apt-get install -y -q python3-venv rsync
    timedatectl set-timezone Europe/Prague
    id agent >/dev/null 2>&1 || useradd --system --create-home --shell /usr/sbin/nologin agent
    mkdir -p $ADRESAR/data"
fi

echo "→ Nahrávám kód, znalostní bázi a klíče…"
rsync -az --delete \
  --exclude .venv/ --exclude __pycache__/ --exclude .git/ --exclude .DS_Store --exclude 'data/' \
  ./ "$CIL:$ADRESAR/"
if [ "${2:-}" = "--prvni" ]; then
  echo "→ Přenáším databázi agenta (co už vyřídil, rozpracované návrhy)…"
  rsync -az data/agent.db "$CIL:$ADRESAR/data/"
fi

echo "→ Instaluji knihovny a (re)startuji agenta…"
ssh "$CIL" "set -e
  cd $ADRESAR
  [ -d .venv ] || python3 -m venv .venv
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -q -r requirements.txt
  chmod 600 .env
  chown -R agent:agent $ADRESAR
  cp server/airbnb-agent.service server/airbnb-panel.service /etc/systemd/system/
  systemctl daemon-reload
  systemctl enable -q airbnb-agent airbnb-panel
  systemctl restart airbnb-agent airbnb-panel
  sleep 5
  systemctl is-active airbnb-agent airbnb-panel
  .venv/bin/python -m agent kontrola | head -6"

echo
echo "✅ Hotovo. Agent běží na serveru $SERVER."
echo "   Ovládací panel: ssh -N -L 8765:localhost:8765 $CIL   a pak v prohlížeči http://localhost:8765"
echo "   Log agenta:     ssh $CIL journalctl -u airbnb-agent -f"

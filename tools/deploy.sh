#!/usr/bin/env bash
# Copia o sistema para a placa pelo USB (precisa do mpremote: pip install mpremote).
# Não mexe em /data (configuração, conversa, memória), /skills nem /programs: o que a placa aprendeu fica.
set -euo pipefail
PORT="${1:-/dev/ttyACM0}"
cd "$(dirname "$0")/.."
python3 tools/build_web.py
MP="mpremote connect $PORT"
$MP exec "import os
for d in ('core', 'lib', 'www', 'www/fonts', 'data', 'skills', 'programs'):
    try:
        os.mkdir(d)
    except OSError:
        pass"
$MP fs cp -r board/core :
$MP fs cp -r board/lib :
$MP fs cp -r board/www :
$MP fs cp board/main.py board/boot.py :
$MP reset
echo "Pronto. A placa reinicia e mostra o endereço na serial (e na OLED, se houver)."

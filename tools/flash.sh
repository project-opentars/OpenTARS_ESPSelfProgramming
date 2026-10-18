#!/usr/bin/env bash
# Grava o MicroPython num ESP32-S3 com PSRAM octal (apaga TUDO o que estava na placa).
# Uso: tools/flash.sh [porta] [arquivo.bin]   (padrões: /dev/ttyACM0 e o .bin mais novo em firmware/)
set -euo pipefail
PORT="${1:-/dev/ttyACM0}"
BIN="${2:-$(ls -t "$(dirname "$0")/../firmware/"*.bin 2>/dev/null | head -1)}"
[ -f "$BIN" ] || { echo "Baixe o firmware ESP32_GENERIC_S3-SPIRAM_OCT de https://micropython.org/download/ESP32_GENERIC_S3/ para firmware/"; exit 1; }
ESPTOOL="$(command -v esptool || command -v esptool.py || ls ~/.arduino15/packages/esp32/tools/esptool_py/*/esptool 2>/dev/null | tail -1)"
"$ESPTOOL" --chip esp32s3 --port "$PORT" erase-flash
"$ESPTOOL" --chip esp32s3 --port "$PORT" write-flash 0 "$BIN"

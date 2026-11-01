#!/usr/bin/env bash
# Instala o openTARS Self-Programming como serviço do seu usuário num Linux (Raspberry Pi OS, Armbian, Ubuntu, Debian, Fedora...).
# Sem sudo. Remover: sbc/install.sh --remove (os dados em ~/.local/share/opentars-sp ficam).
# GPIO e I2C: sbc/install.sh --hardware (esse pede sudo).
set -euo pipefail
cd "$(dirname "$0")/.."
REPO="$(pwd)"
PORT="${OPENTARS_PORT:-8080}"
UNIT="$HOME/.config/systemd/user/opentars-sp.service"

if [ "${1:-}" = "--remove" ]; then
  systemctl --user disable --now opentars-sp 2>/dev/null || true
  rm -f "$UNIT"
  systemctl --user daemon-reload 2>/dev/null || true
  echo "Removed. Your data is still in ~/.local/share/opentars-sp."
  exit 0
fi

if [ "${1:-}" = "--hardware" ]; then
  # GPIO e I2C para o seu usuário (pede sudo uma vez): bibliotecas, regra do udev e grupos
  echo "This uses sudo to: install python3-libgpiod, gpiod and i2c-tools, let the groups gpio and i2c use /dev/gpiochip* and /dev/i2c-*, and add $USER to them."
  if command -v apt-get >/dev/null; then sudo apt-get install -y python3-libgpiod gpiod i2c-tools; fi
  sudo groupadd -f gpio
  sudo groupadd -f i2c
  printf '%s\n' 'SUBSYSTEM=="gpio", KERNEL=="gpiochip*", GROUP="gpio", MODE="0660"' \
    'SUBSYSTEM=="i2c-dev", KERNEL=="i2c-[0-9]*", GROUP="i2c", MODE="0660"' | sudo tee /etc/udev/rules.d/60-opentars-gpio.rules >/dev/null
  sudo udevadm control --reload-rules
  sudo udevadm trigger
  sudo usermod -aG gpio,i2c "$USER"
  echo "Done. Reboot the board (sudo reboot) so the new groups reach openTARS."
  exit 0
fi

command -v python3 >/dev/null || { echo "Python 3 is required (sudo apt install python3)."; exit 1; }
python3 -c 'import sys; sys.exit(sys.version_info < (3, 8))' || { echo "Python 3.8 or newer is required."; exit 1; }
python3 tools/build_web.py

if ! systemctl --user show-environment >/dev/null 2>&1; then
  echo "No systemd user session here. Run it by hand instead:  python3 $REPO/sbc/opentars_sbc.py"
  exit 0
fi
mkdir -p "$(dirname "$UNIT")"
cat > "$UNIT" <<UNITEOF
[Unit]
Description=openTARS Self-Programming
After=network-online.target

[Service]
ExecStart=$(command -v python3) $REPO/sbc/opentars_sbc.py
Environment=OPENTARS_PORT=$PORT
Restart=on-failure
RestartSec=3

[Install]
WantedBy=default.target
UNITEOF
systemctl --user daemon-reload
systemctl --user enable --now opentars-sp
# sem isto o serviço só roda enquanto você está logado
loginctl enable-linger "$USER" 2>/dev/null || echo "To start it at boot without logging in, run once: sudo loginctl enable-linger $USER"

IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
echo
echo "openTARS Self-Programming is running: http://${IP:-<this computer>}:$PORT"
echo "Open it on your phone, copy the connect command and run it on a computer with claude, codex, opencode, pi or grok (it can be this one)."
echo "For GPIO and I2C, run once: sbc/install.sh --hardware"
echo "WARNING: there is no password. Anyone on this network can open that page and run commands as $USER."

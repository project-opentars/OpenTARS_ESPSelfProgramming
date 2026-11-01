# openTARS Self-Programming

> Ask for something from your phone, and the AI program you already have on your computer writes the code and runs it on your microcontroller.

You open the board's web page and say "make the LED breathe" or "show a spinning cube on the screen". A tiny bridge on your computer hands the request to the AI program you already use (**Claude Code, Codex, OpenCode, Pi, Grok Build**), which writes MicroPython and runs it on the board, reads the errors and fixes them. No API keys, no model settings: whatever those programs are logged in to is what you use.

- **Light.** The board only serves the page and runs programs. The bridge is one Python file with no dependencies.
- **Any board with MicroPython + Wi-Fi.** Tested on one ESP32-S3 (see Status). Pins (OLED, LED) are settings.
- **Self-programming.** Reusable modules go to `/skills`; facts to the board's notes.
- **Boards talk to each other** over ESP-NOW (no router needed).
- Phone-friendly page in English and Portuguese, file editor, program manager with logs, start-on-power-on.

## Quick start

1. Flash MicroPython (this **erases** the board; use the image for your chip from [micropython.org](https://micropython.org/download/)): `tools/flash.sh /dev/ttyACM0`
2. Copy the system: `pip install mpremote`, then `tools/deploy.sh /dev/ttyACM0`
3. On your phone, join the open Wi-Fi **opentars-xxxx**, open **http://192.168.71.1**, go to **Settings > Wi-Fi**, pick your network and connect. The page shows the new address; put your phone back on your Wi-Fi and open it.
4. The page shows one command to copy. Paste it in a terminal **on the computer that has the AI program installed** (and logged in). Leave it open:
   ```
   curl -fsS http://<board address>/bridge.py -o bridge.py && python3 bridge.py http://<board address>
   ```
   Next time just run `python3 bridge.py`: it remembers the board.
5. Chat. Under **Settings** you can pick which AI program to use and a model name (empty = the program's default).

## Raspberry Pi, Orange Pi and other Linux boards

The same system runs on any Linux single-board computer (Raspberry Pi, Orange Pi, Rock, Banana Pi, Jetson...) or any Linux PC, with Python 3.8+ and nothing else to install. There the AI also works with Linux itself: it runs Python 3 programs and **shell commands** (`run_shell`), and uses the GPIO and I2C tools and libraries that are installed.

```
git clone https://github.com/project-opentars/OpenTARS_ESPSelfProgramming
cd OpenTARS_ESPSelfProgramming
sbc/install.sh
```

It installs a systemd **user** service (no sudo), on port 8080, and prints the address. Open it on your phone, copy the connect command and run it on a computer with an AI program; that can be the board itself, if the AI program runs there. Without systemd: `python3 sbc/opentars_sbc.py`. Remove: `sbc/install.sh --remove` (your data stays in `~/.local/share/opentars-sp`). Settings: `OPENTARS_PORT`, `OPENTARS_HOME`.

**GPIO and I2C:** run `sbc/install.sh --hardware` once (it uses sudo: installs `python3-libgpiod`, `gpiod` and `i2c-tools`, lets the groups `gpio` and `i2c` use the devices through a udev rule, adds you to them) and reboot. Programs then use the `sbc` helper, which works with libgpiod v1 (Debian 12) and v2:

```python
import sbc
led = sbc.Pin("PC5", out=True)   # by line name; on Allwinner boards (Orange Pi) PC5 works even when the kernel names no lines
led.toggle()
button = sbc.Pin("PC6", pull="up"); button.value()
sbc.info()                       # model, temperature, memory, disk, GPIO chips and I2C buses this user can open
```

The AI runs commands as your user, without sudo, and is told not to install system packages or run destructive commands. **There is no password: anyone on your network who opens the page can run commands on that computer as your user.** Use it only on a network you trust.

## How it works

```
phone ──HTTP──▶ board (MicroPython: page, programs, ESP-NOW)
                  ▲  │ request queue
                  │  ▼
           bridge.py on your computer ──runs──▶ claude / codex / opencode / pi / grok
                  ▲                                   │
                  └──── python3 bridge.py tool ... ◀──┘  (how the AI program acts on the board: run_code, start_program, write_file, ...)
```

The bridge asks the board for work (so the board never needs your computer's address), starts the AI program once per request in an empty temporary folder, gives it the board's guide and the last few messages, and sends its final reply back to the page. Stop on the page stops it. "stop" and "pare tudo" are handled by the board itself.

Programs must call `delay(ms)` inside loops; that is how they can be stopped. The AI can write to `/skills`, `/programs`, `/data/files` and its notes; system files are protected (editable from the **Code** tab with developer mode on). **Safe mode:** hold BOOT while powering on to skip programs that start automatically.

## Status

Early release. On one ESP32-S3 (8 MB octal PSRAM, 16 MB flash) with real AI programs: **Claude Code, Codex, OpenCode and Grok Build** each ran a request end to end (page → bridge → AI program → code on the board). **Pi** starts correctly but was not logged in on the test machine, so it was not run to the end. **Ollama is not supported**: it only answers text and cannot act on the board by itself. ESP-NOW has only been tested with simulated boards. **Linux boards:** tested only on an x86-64 Linux PC standing in for one (same Python code, end to end with Claude Code and `run_shell`); not yet run on a real Raspberry Pi, Orange Pi or other ARM board, and `sbc/install.sh` was not run on a real board. The `sbc` GPIO helper was checked against the real libgpiod v2 API (and the v1.6 source) and with simulated chips, but never switched a real pin. Only Linux was tried for the bridge; it uses nothing Linux-specific, but macOS/Windows are untested.

## Security

- **No password** on the board: anyone on the same Wi-Fi can open the page and run code on it. ESP-NOW is not encrypted.
- The AI programs run with their permissions relaxed so they can run the board commands without asking (Claude: `Bash` allowed; Codex: workspace sandbox with network; OpenCode `--auto`; Grok `--always-approve`), starting in an empty temp folder. That is the same trust you give them in your own terminal; do not run the bridge if you do not want that.

## Development

- `python3 tests/test_core.py`: page, bridge end to end with a fake `claude`, threads, tools, two simulated ESP-NOW boards.
- `mpremote connect /dev/ttyACM0 run tests/smoke_board.py`: smoke test on the real board (threads, OLED, LED).
- `python3 tools/dev_server.py` + `python3 pc/bridge.py http://127.0.0.1:8090`: page and API on your computer.

## License

MIT. The SSD1306 driver follows the micropython-lib driver (MIT). IBM Plex fonts: SIL Open Font License (`web/fonts/OFL.txt`).

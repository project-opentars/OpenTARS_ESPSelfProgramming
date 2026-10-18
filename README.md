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

Early release. On one ESP32-S3 (8 MB octal PSRAM, 16 MB flash) with real AI programs: **Claude Code, Codex, OpenCode and Grok Build** each ran a request end to end (page → bridge → AI program → code on the board). **Pi** starts correctly but was not logged in on the test machine, so it was not run to the end. **Ollama is not supported**: it only answers text and cannot act on the board by itself. ESP-NOW has only been tested with simulated boards. Only Linux was tried for the bridge; it uses nothing Linux-specific, but macOS/Windows are untested.

## Security

- **No password** on the board: anyone on the same Wi-Fi can open the page and run code on it. ESP-NOW is not encrypted.
- The AI programs run with their permissions relaxed so they can run the board commands without asking (Claude: `Bash` allowed; Codex: workspace sandbox with network; OpenCode `--auto`; Grok `--always-approve`), starting in an empty temp folder. That is the same trust you give them in your own terminal; do not run the bridge if you do not want that.

## Development

- `python3 tests/test_core.py`: page, bridge end to end with a fake `claude`, threads, tools, two simulated ESP-NOW boards.
- `mpremote connect /dev/ttyACM0 run tests/smoke_board.py`: smoke test on the real board (threads, OLED, LED).
- `python3 tools/dev_server.py` + `python3 pc/bridge.py http://127.0.0.1:8090`: page and API on your computer.

## License

MIT. The SSD1306 driver follows the micropython-lib driver (MIT). IBM Plex fonts: SIL Open Font License (`web/fonts/OFL.txt`).
